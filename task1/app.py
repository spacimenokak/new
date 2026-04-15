import os
from decimal import Decimal

import psycopg2


class StoreDB:
    def __init__(self):
        self.connection = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5432),
            database=os.getenv("DB_NAME", "store"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
        )
        self.connection.autocommit = False

    def place_order(self, customer_id, order_items):
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT customerid FROM customers WHERE customerid = %s",
                (customer_id,),
            )
            if cursor.fetchone() is None:
                raise ValueError(f"Клиент с id {customer_id} не найден.")

            cursor.execute(
                "INSERT INTO orders (customerid, totalamount) VALUES (%s, %s) RETURNING orderid",
                (customer_id, Decimal("0")),
            )
            order_id = cursor.fetchone()[0]

            total_amount = Decimal("0")

            for item in order_items:
                cursor.execute(
                    "SELECT price FROM products WHERE productid = %s",
                    (item["product_id"],),
                )
                product_row = cursor.fetchone()
                if product_row is None:
                    raise ValueError(f"Товар с id {item['product_id']} не найден.")

                price = Decimal(product_row[0])
                quantity = int(item["quantity"])
                if quantity <= 0:
                    raise ValueError("Количество товара должно быть больше 0.")

                subtotal = price * Decimal(quantity)
                total_amount += subtotal

                cursor.execute(
                    "INSERT INTO order_items (orderid, productid, quantity, subtotal) VALUES (%s, %s, %s, %s)",
                    (order_id, item["product_id"], quantity, subtotal),
                )

            cursor.execute(
                "UPDATE orders SET totalamount = %s WHERE orderid = %s",
                (total_amount, order_id),
            )

            self.connection.commit()
            print(f"Заказ {order_id} создан. Общая сумма: {total_amount:.2f}.")
            return order_id
        except Exception:
            self.connection.rollback()
            raise

    def update_customer_email(self, customer_id, new_email):
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT email FROM customers WHERE customerid = %s",
                (customer_id,),
            )
            old_email_row = cursor.fetchone()
            if old_email_row is None:
                raise ValueError(f"Клиент с id {customer_id} не найден.")

            cursor.execute(
                "SELECT customerid FROM customers WHERE email = %s AND customerid <> %s",
                (new_email, customer_id),
            )
            if cursor.fetchone() is not None:
                raise ValueError(f"Email {new_email} уже используется другим клиентом.")

            cursor.execute(
                "UPDATE customers SET email = %s WHERE customerid = %s",
                (new_email, customer_id),
            )
            self.connection.commit()
            print(f"Email клиента {customer_id} обновлён с {old_email_row[0]} на {new_email}.")
        except Exception:
            self.connection.rollback()
            raise

    def add_product(self, name, price):
        try:
            if not name or not str(name).strip():
                raise ValueError("Название продукта не может быть пустым.")

            price = Decimal(price)
            if price < 0:
                raise ValueError("Цена не может быть отрицательной.")

            cursor = self.connection.cursor()
            cursor.execute(
                "INSERT INTO products (productname, price) VALUES (%s, %s) RETURNING productid",
                (name.strip(), price),
            )
            product_id = cursor.fetchone()[0]
            self.connection.commit()
            print(f"Продукт '{name}' добавлен с id {product_id} и ценой {price:.2f}.")
            return product_id
        except Exception:
            self.connection.rollback()
            raise

    def close(self):
        if self.connection:
            self.connection.close()


if __name__ == "__main__":
    db = StoreDB()
    try:
        print("\n=== СЦЕНАРИЙ 1: Размещение заказа ===")
        order_items = [
            {"product_id": 1, "quantity": 1},
            {"product_id": 2, "quantity": 2},
        ]
        db.place_order(customer_id=1, order_items=order_items)

        print("\n=== СЦЕНАРИЙ 2: Обновление email ===")
        db.update_customer_email(customer_id=1, new_email="ivan.new@example.com")

        print("\n=== СЦЕНАРИЙ 3: Добавление товара ===")
        db.add_product(name="Наушники", price="2500.00")
    finally:
        db.close()
