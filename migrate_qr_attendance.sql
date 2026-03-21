-- ============================================================
-- MIGRATION: QR Attendance System
-- Run: mysql -u root -p club_portal_v11 < migrate_qr_attendance.sql
-- ============================================================

USE club_portal_v11;

-- Table 1: event_attendance (may already exist — safe IF NOT EXISTS)
CREATE TABLE IF NOT EXISTS event_attendance (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    event_id   INT NOT NULL,
    user_id    INT NOT NULL,
    marked_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (event_id, user_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
    INDEX idx_event_attendance (event_id),
    INDEX idx_user_attendance  (user_id)
);

-- Table 2: qr_sessions — stores the active QR session per event
-- One active session per event at a time
-- token:      HMAC-signed rotating value (changes every 30 seconds)
-- seed:       random seed used in HMAC (set when coordinator clicks Generate)
-- expires_at: 10 minutes after generation
CREATE TABLE IF NOT EXISTS qr_sessions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    event_id    INT NOT NULL UNIQUE,          -- one session per event
    seed        VARCHAR(64)  NOT NULL,        -- random seed for HMAC
    generated_by INT NOT NULL,               -- coordinator who generated
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at   TIMESTAMP NOT NULL,         -- generated_at + 10 minutes
    is_active    BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (event_id)    REFERENCES events(id) ON DELETE CASCADE,
    FOREIGN KEY (generated_by) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_qr_event (event_id),
    INDEX idx_qr_expires (expires_at)
);

SELECT 'QR attendance migration complete' AS status;
