-- MySQL 8+ normalized core schema (illustrative; generated CSVs contain full columns)
CREATE DATABASE IF NOT EXISTS seller_ops;
USE seller_ops;

CREATE TABLE IF NOT EXISTS seller (
  seller_id VARCHAR(20) PRIMARY KEY,
  seller_name VARCHAR(120) NOT NULL,
  status ENUM('active','suspended','onboarding') NOT NULL,
  created_at DATETIME NOT NULL,
  suspended_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS product_listing (
  listing_id VARCHAR(80) PRIMARY KEY,
  seller_id VARCHAR(20) NOT NULL,
  product_name VARCHAR(120) NOT NULL,
  category VARCHAR(40) NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD',
  status ENUM('active','inactive','removed') NOT NULL,
  created_at DATETIME NOT NULL,
  CONSTRAINT fk_listing_seller FOREIGN KEY (seller_id) REFERENCES seller(seller_id)
);

CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR(20) PRIMARY KEY,
  order_date DATETIME NOT NULL,
  order_status ENUM('placed','shipped','delivered','cancelled','returned') NOT NULL,
  order_total DECIMAL(14,2) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS order_line (
  order_line_id VARCHAR(80) PRIMARY KEY,
  order_id VARCHAR(20) NOT NULL,
  listing_id VARCHAR(80) NOT NULL,
  seller_id VARCHAR(20) NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  line_total DECIMAL(14,2) NOT NULL,
  CONSTRAINT fk_line_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_line_listing FOREIGN KEY (listing_id) REFERENCES product_listing(listing_id),
  CONSTRAINT fk_line_seller FOREIGN KEY (seller_id) REFERENCES seller(seller_id)
);

CREATE TABLE IF NOT EXISTS fulfillment (
  fulfillment_id VARCHAR(100) PRIMARY KEY,
  order_line_id VARCHAR(80) NOT NULL UNIQUE,
  status ENUM('pending','shipped','delivered','returned') NOT NULL,
  shipped_at DATETIME NULL,
  delivered_at DATETIME NULL,
  expected_ship_at DATETIME NOT NULL,
  CONSTRAINT fk_fulfillment_line FOREIGN KEY (order_line_id) REFERENCES order_line(order_line_id)
);

CREATE TABLE IF NOT EXISTS customer_review (
  review_id VARCHAR(30) PRIMARY KEY,
  order_line_id VARCHAR(80) NOT NULL UNIQUE,
  rating TINYINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review_date DATETIME NOT NULL,
  CONSTRAINT fk_review_line FOREIGN KEY (order_line_id) REFERENCES order_line(order_line_id)
);

CREATE TABLE IF NOT EXISTS dispute (
  dispute_id VARCHAR(20) PRIMARY KEY,
  order_id VARCHAR(20) NOT NULL,
  dispute_date DATETIME NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  status ENUM('open','won','lost','resolved') NOT NULL,
  CONSTRAINT fk_dispute_order FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE TABLE IF NOT EXISTS commission_rule (
  rule_id VARCHAR(30) PRIMARY KEY,
  category VARCHAR(40) NOT NULL,
  rate DECIMAL(6,5) NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE NULL
);

CREATE TABLE IF NOT EXISTS payout (
  payout_id VARCHAR(30) PRIMARY KEY,
  seller_id VARCHAR(20) NOT NULL,
  payout_date DATETIME NOT NULL,
  recorded_total DECIMAL(14,2) NOT NULL,
  status ENUM('eligible','held','paid','blocked') NOT NULL,
  CONSTRAINT fk_payout_seller FOREIGN KEY (seller_id) REFERENCES seller(seller_id)
);

CREATE TABLE IF NOT EXISTS payout_line (
  payout_line_id VARCHAR(100) PRIMARY KEY,
  payout_id VARCHAR(30) NOT NULL,
  order_line_id VARCHAR(80) NULL,
  line_type ENUM('sale','commission','refund','dispute','reserve_hold','reserve_release','prior_payment','adjustment') NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  dispute_id VARCHAR(20) NULL,
  CONSTRAINT fk_payoutline_payout FOREIGN KEY (payout_id) REFERENCES payout(payout_id),
  CONSTRAINT fk_payoutline_orderline FOREIGN KEY (order_line_id) REFERENCES order_line(order_line_id),
  CONSTRAINT fk_payoutline_dispute FOREIGN KEY (dispute_id) REFERENCES dispute(dispute_id)
);

-- Append-only history is represented in seller_events.csv and fulfillment_events.csv.
-- Add database event tables/triggers if enforcing immutable audit history inside MySQL.
