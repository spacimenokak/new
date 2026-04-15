create table if not exists customers (
    customerid serial primary key,
    firstname varchar(255) not null,
    lastname varchar(255) not null,
    email varchar(255) unique not null
);

create table if not exists products (
    productid serial primary key,
    productname varchar(255) not null unique,
    price decimal(10, 2) not null check (price >= 0)
);

create table if not exists orders (
    orderid serial primary key,
    customerid int not null references customers(customerid),
    orderdate timestamp default current_timestamp,
    totalamount decimal(10, 2) not null default 0 check (totalamount >= 0)
);

create table if not exists order_items (
    orderitemid serial primary key,
    orderid int not null references orders(orderid),
    productid int not null references products(productid),
    quantity int not null check (quantity > 0),
    subtotal decimal(10, 2) not null check (subtotal >= 0)
);

insert into customers (firstname, lastname, email) values
('Мария', 'Рязанова', 'pal.palych@internet.ru')
on conflict (email) do nothing;

insert into products (productname, price) values
('Товар 1', 10.00),
('Товар 2', 20.00),
('Товар 3', 30.00)
on conflict (productname) do nothing;