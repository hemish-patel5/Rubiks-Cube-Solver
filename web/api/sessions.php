<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');

function respond(int $status, array $body): never
{
    http_response_code($status);
    echo json_encode($body, JSON_UNESCAPED_SLASHES);
    exit;
}

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['ok' => false, 'error' => 'POST required']);
}

$configuredKey = getenv('RUBIKS_API_KEY');
$providedKey = $_SERVER['HTTP_X_API_KEY'] ?? '';
if (!is_string($configuredKey) || $configuredKey === '') {
    respond(500, ['ok' => false, 'error' => 'Server authentication is not configured']);
}
if (!hash_equals($configuredKey, $providedKey)) {
    respond(401, ['ok' => false, 'error' => 'Unauthorized']);
}

$contentLength = (int) ($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($contentLength > 32768) {
    respond(413, ['ok' => false, 'error' => 'Payload too large']);
}
$rawBody = file_get_contents('php://input', false, null, 0, 32769);
if ($rawBody !== false && strlen($rawBody) > 32768) {
    respond(413, ['ok' => false, 'error' => 'Payload too large']);
}
$payload = json_decode($rawBody === false ? '' : $rawBody, true);
if (!is_array($payload)) {
    respond(400, ['ok' => false, 'error' => 'A JSON object is required']);
}

$allowedKeys = [
    'session_id', 'started_at', 'finished_at', 'status', 'facelets_urfdlb',
    'moves', 'move_count', 'solve_duration_seconds', 'error_message',
];
$requiredKeys = ['session_id', 'started_at', 'finished_at', 'status', 'moves', 'move_count'];
if (array_diff(array_keys($payload), $allowedKeys) !== []) {
    respond(422, ['ok' => false, 'error' => 'Unexpected payload field']);
}
if (array_diff($requiredKeys, array_keys($payload)) !== []) {
    respond(422, ['ok' => false, 'error' => 'Missing required payload field']);
}

$sessionId = $payload['session_id'];
$status = $payload['status'];
$facelets = $payload['facelets_urfdlb'] ?? null;
$moves = $payload['moves'];
$moveCount = $payload['move_count'];
$duration = $payload['solve_duration_seconds'] ?? null;
$errorMessage = $payload['error_message'] ?? null;

if (!is_string($sessionId) || !preg_match('/^[A-Za-z0-9-]{1,64}$/', $sessionId)) {
    respond(422, ['ok' => false, 'error' => 'Invalid session_id']);
}
if (!is_string($status) || !in_array($status, ['COMPLETE', 'ERROR', 'CANCELLED'], true)) {
    respond(422, ['ok' => false, 'error' => 'Invalid status']);
}
if ($facelets !== null && (!is_string($facelets) || !preg_match('/^[URFDLB]{54}$/', $facelets))) {
    respond(422, ['ok' => false, 'error' => 'Invalid facelets_urfdlb']);
}
if ($facelets !== null) {
    foreach (str_split('URFDLB') as $face) {
        if (substr_count($facelets, $face) !== 9) {
            respond(422, ['ok' => false, 'error' => 'Invalid facelet counts']);
        }
    }
}
if ($status === 'COMPLETE' && $facelets === null) {
    respond(422, ['ok' => false, 'error' => 'Completed runs require facelets']);
}
if (!is_array($moves) || !array_is_list($moves) || !is_int($moveCount) || $moveCount !== count($moves)) {
    respond(422, ['ok' => false, 'error' => 'Invalid moves']);
}
foreach ($moves as $move) {
    if (!is_string($move) || !preg_match("/^[URFDLB](?:2|')?$/", $move)) {
        respond(422, ['ok' => false, 'error' => 'Invalid move token']);
    }
}
if ($duration !== null && (!is_int($duration) && !is_float($duration) || $duration < 0)) {
    respond(422, ['ok' => false, 'error' => 'Invalid solve duration']);
}
if ($errorMessage !== null && (!is_string($errorMessage) || strlen($errorMessage) > 500)) {
    respond(422, ['ok' => false, 'error' => 'Invalid error message']);
}

if (!is_string($payload['started_at']) || !is_string($payload['finished_at'])) {
    respond(422, ['ok' => false, 'error' => 'Invalid timestamp']);
}
try {
    $startedAt = (new DateTimeImmutable((string) $payload['started_at']))
        ->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
    $finishedAt = (new DateTimeImmutable((string) $payload['finished_at']))
        ->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
} catch (Exception) {
    respond(422, ['ok' => false, 'error' => 'Invalid timestamp']);
}

$host = getenv('RUBIKS_DB_HOST') ?: '127.0.0.1';
$port = getenv('RUBIKS_DB_PORT') ?: '3306';
$database = getenv('RUBIKS_DB_NAME');
$username = getenv('RUBIKS_DB_USER');
$password = getenv('RUBIKS_DB_PASSWORD');
if (!$database || !$username || $password === false) {
    respond(500, ['ok' => false, 'error' => 'Database is not configured']);
}

try {
    $pdo = new PDO(
        "mysql:host={$host};port={$port};dbname={$database};charset=utf8mb4",
        $username,
        $password,
        [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]
    );
    $statement = $pdo->prepare(
        'INSERT INTO solve_runs (
            session_id, started_at, finished_at, terminal_status, facelets_urfdlb,
            moves_json, move_count, solve_duration_seconds, error_message
        ) VALUES (
            :session_id, :started_at, :finished_at, :terminal_status, :facelets_urfdlb,
            :moves_json, :move_count, :solve_duration_seconds, :error_message
        ) ON DUPLICATE KEY UPDATE
            started_at = VALUES(started_at),
            finished_at = VALUES(finished_at),
            terminal_status = VALUES(terminal_status),
            facelets_urfdlb = VALUES(facelets_urfdlb),
            moves_json = VALUES(moves_json),
            move_count = VALUES(move_count),
            solve_duration_seconds = VALUES(solve_duration_seconds),
            error_message = VALUES(error_message)'
    );
    $statement->execute([
        'session_id' => $sessionId,
        'started_at' => $startedAt,
        'finished_at' => $finishedAt,
        'terminal_status' => $status,
        'facelets_urfdlb' => $facelets,
        'moves_json' => json_encode($moves, JSON_THROW_ON_ERROR),
        'move_count' => $moveCount,
        'solve_duration_seconds' => $duration,
        'error_message' => $errorMessage,
    ]);
    respond(200, ['ok' => true, 'session_id' => $sessionId]);
} catch (Throwable) {
    respond(500, ['ok' => false, 'error' => 'Database write failed']);
}
