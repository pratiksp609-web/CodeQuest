-- Create the database and a user for the app, then run `python manage.py init`
-- which creates the tables through SQLAlchemy.
CREATE DATABASE IF NOT EXISTS learnopt CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'learnopt'@'localhost' IDENTIFIED BY 'learnopt';
GRANT ALL PRIVILEGES ON learnopt.* TO 'learnopt'@'localhost';
FLUSH PRIVILEGES;
