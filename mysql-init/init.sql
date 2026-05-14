-- Databases for each OpenMetadata instance
CREATE DATABASE IF NOT EXISTS openmetadata_site_a CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS openmetadata_site_b CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS openmetadata_central CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Single shared user with access to all three
CREATE USER IF NOT EXISTS 'openmetadata_user'@'%' IDENTIFIED BY 'openmetadata_password';
GRANT ALL PRIVILEGES ON openmetadata_site_a.* TO 'openmetadata_user'@'%';
GRANT ALL PRIVILEGES ON openmetadata_site_b.* TO 'openmetadata_user'@'%';
GRANT ALL PRIVILEGES ON openmetadata_central.* TO 'openmetadata_user'@'%';
FLUSH PRIVILEGES;
