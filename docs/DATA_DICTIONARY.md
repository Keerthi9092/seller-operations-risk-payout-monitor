# Data dictionary

Money values are stored as integer cents in generated CSVs (100 cents = USD 1.00). Timestamps use `YYYY-MM-DD HH:MM:SS` and synthetic dates. IDs are strings and immutable.

| Entity / file | Primary key | Required fields | Optional fields / rules |
|---|---|---|---|
| Seller / `sellers.csv` | `seller_id` (`SELL-000001`) | `seller_name`, `status`, `created_at` | `suspended_at`; status is active/suspended/onboarding; tier is standard/priority/managed |
| ProductListing / `product_listings.csv` | `listing_id` (`LIST-SELL-000001-000001`) | `seller_id`, `product_name`, `category`, `price_cents`, `currency`, `status`, `created_at` | Valid seller FK; cents >= 0; anomaly labels are kept in `ground_truth.csv` only |
| Order / `orders.csv` | `order_id` (`ORD-2026-000001`) | `order_date`, `order_status`, `order_total_cents`, `currency` | status placed/shipped/delivered/cancelled/returned; total equals sum of lines |
| OrderLine / `order_lines.csv` | `order_line_id` (`OL-000001-01`) | `order_id`, `listing_id`, `seller_id`, `quantity`, `unit_price_cents`, `line_total_cents` | quantity > 0; line total = quantity × unit price; valid FKs |
| Fulfillment / `fulfillments.csv` | `fulfillment_id` (`FUL-OL-000001-01`) | `order_line_id`, `status`, `expected_ship_at` | shipped/delivered timestamps optional until lifecycle advances; one fulfillment per line in base design; anomaly labels are kept in `ground_truth.csv` only |
| CustomerReview / `customer_reviews.csv` | `review_id` | `order_line_id`, `rating`, `review_date` | optional per line; rating integer 1–5; at most one review per line |
| Dispute / `disputes.csv` | `dispute_id` (`DSP-2026-000001`) | `order_id`, `dispute_date`, `amount_cents`, `status` | status open/won/lost/resolved; amount > 0; `deduction_expected` derived from documented policy |
| CommissionRule / `commission_rules.csv` | `rule_id` | `category`, `rate`, `effective_from` | `effective_to` optional; rate is fraction (e.g. 0.10 = 10%); `reserve_rate` fraction; `hold_days` integer |
| Payout / `payouts.csv` | `payout_id` (`PAYOUT-2026-000001`) | `seller_id`, `payout_date`, `recorded_total_cents`, `status` | status eligible/held/blocked/paid; intentionally mismatched total is a labeled anomaly |
| PayoutLine / `payout_lines.csv` | `payout_line_id` | `payout_id`, `line_type`, `amount_cents` | `order_line_id` optional for seller-level dispute adjustment; nullable `dispute_id` identifies the dispute deduction; signed cents; payout total must equal line sum except injected anomaly |
| Seller event / `seller_events.csv` | `event_id` | `seller_id`, `event_type`, `event_at` | prior/new status; append-only state history |
| Fulfillment event / `fulfillment_events.csv` | `event_id` | `fulfillment_id`, `event_type`, `event_at` | prior/new status; append-only lifecycle events |
| Ground truth / `ground_truth.csv` | `issue_id` | `entity_type`, `record_id`, `issue_type`, `expected_label`, `expected_decision` | evaluation labels only; never used as detector input |

## Cardinality
- Seller 1:N ProductListing.
- Order 1:N OrderLine.
- ProductListing 1:N OrderLine.
- Seller 1:N OrderLine.
- OrderLine 1:0..1 Fulfillment in the base model (generator currently creates one fulfillment per line).
- OrderLine 1:0..1 CustomerReview.
- Order 1:0..N Dispute.
- Seller 1:N Payout; Payout 1:N PayoutLine.
- OrderLine 1:N PayoutLine because split/adjustment accounting is supported.
- Seller and Fulfillment lifecycle transitions are preserved in append-only event exports.

## Lifecycle and financial assumptions
- Seller status: onboarding → active → suspended (or active remains active).
- Fulfillment status: pending → shipped → delivered; returns may be represented as a later event in an extension.
- A payout candidate requires delivery plus 7 days of reserve hold. Commission rate is selected by listing category from the rule effective on the order date.
- Lost/resolved disputes are eligible for deduction in the illustrative policy.
- The generator includes intentional labeled anomalies for evaluation. Treat these as test fixtures, not as valid production financial transactions.
