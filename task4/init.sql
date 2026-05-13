USE isolation;

DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
  id INT PRIMARY KEY AUTO_INCREMENT,
  owner VARCHAR(64) NOT NULL UNIQUE,
  balance INT NOT NULL,
  version INT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

DROP TABLE IF EXISTS counters;
CREATE TABLE counters (
  id INT PRIMARY KEY,
  val INT NOT NULL
) ENGINE=InnoDB;

DROP TABLE IF EXISTS items;
CREATE TABLE items (
  id INT PRIMARY KEY AUTO_INCREMENT,
  category VARCHAR(64) NOT NULL,
  price INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO accounts (owner, balance) VALUES
('alice', 100),
('bob', 100);

INSERT INTO counters (id, val) VALUES
(1, 0);

INSERT INTO items (category, price) VALUES
('book', 120),
('book', 150),
('book', 90),
('toy', 200);

