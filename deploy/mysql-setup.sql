-- sudo mysql < deploy/mysql-setup.sql   (แก้ CHANGE_ME ก่อนรัน)
CREATE DATABASE IF NOT EXISTS labborrow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'labborrow'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON labborrow.* TO 'labborrow'@'localhost';
FLUSH PRIVILEGES;
