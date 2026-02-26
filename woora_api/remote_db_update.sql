-- Add the column (Will throw an error if already exists, but that's fine for our context, or we can use a safe add)

SET @dbname = 'woora_db';
SET @tablename = 'Properties';
SET @columnname = 'share_uid';
SET @preparedStatement = (SELECT IF(
  (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE
      table_schema = @dbname
      AND table_name = @tablename
      AND column_name = @columnname
  ) > 0,
  "SELECT 1",
  CONCAT("ALTER TABLE ", @tablename, " ADD COLUMN ", @columnname, " VARCHAR(20) UNIQUE DEFAULT NULL;")
));
PREPARE alterIfNotExists FROM @preparedStatement;
EXECUTE alterIfNotExists;
DEALLOCATE PREPARE alterIfNotExists;


DROP FUNCTION IF EXISTS generate_base36_timestamp;
DELIMITER $$
CREATE FUNCTION generate_base36_timestamp() RETURNS VARCHAR(20) DETERMINISTIC
BEGIN
  DECLARE chars VARCHAR(36) DEFAULT '0123456789abcdefghijklmnopqrstuvwxyz';
  DECLARE val BIGINT;
  DECLARE res VARCHAR(20) DEFAULT '';
  DECLARE rnd INT;
  
  SET val = (UNIX_TIMESTAMP() * 1000000) + MICROSECOND(NOW(6)) + FLOOR(RAND() * 1000);
  
  WHILE val > 0 DO
    SET res = CONCAT(SUBSTRING(chars, (val MOD 36) + 1, 1), res);
    SET val = FLOOR(val / 36);
  END WHILE;
  
  SET rnd = FLOOR(RAND() * 36) + 1;
  SET res = CONCAT(res, SUBSTRING(chars, rnd, 1));
  SET rnd = FLOOR(RAND() * 36) + 1;
  SET res = CONCAT(res, SUBSTRING(chars, rnd, 1));
  
  RETURN res;
END$$
DELIMITER ;

UPDATE Properties SET share_uid = generate_base36_timestamp() WHERE share_uid IS NULL;
