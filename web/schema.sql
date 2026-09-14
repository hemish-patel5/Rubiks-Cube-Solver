CREATE TABLE IF NOT EXISTS solve_runs (
    session_id VARCHAR(64) PRIMARY KEY,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NOT NULL,
    terminal_status ENUM('COMPLETE', 'ERROR', 'CANCELLED') NOT NULL,
    facelets_urfdlb CHAR(54) NULL,
    moves_json JSON NOT NULL,
    move_count SMALLINT UNSIGNED NOT NULL,
    solve_duration_seconds DECIMAL(10, 3) NULL,
    error_message VARCHAR(500) NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_finished_at (finished_at),
    INDEX idx_terminal_status (terminal_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
