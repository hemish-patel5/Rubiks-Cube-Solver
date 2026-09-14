<?php
declare(strict_types=1);

function h(mixed $value): string
{
    return htmlspecialchars((string) $value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

$host = getenv('RUBIKS_DB_HOST') ?: '127.0.0.1';
$port = getenv('RUBIKS_DB_PORT') ?: '3306';
$database = getenv('RUBIKS_DB_NAME');
$username = getenv('RUBIKS_DB_READ_USER');
$password = getenv('RUBIKS_DB_READ_PASSWORD');
$configurationError = null;
$summary = ['total_attempts' => 0, 'completed_solves' => 0, 'success_rate' => 0,
    'average_move_count' => null, 'average_solve_time' => null];
$recent = [];
$errors = [];

try {
    if (!$database || !$username || $password === false) {
        throw new RuntimeException('Read-only database access is not configured.');
    }
    $pdo = new PDO(
        "mysql:host={$host};port={$port};dbname={$database};charset=utf8mb4",
        $username,
        $password,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]
    );
    $summary = $pdo->query(
        "SELECT COUNT(*) AS total_attempts,
                SUM(terminal_status = 'COMPLETE') AS completed_solves,
                ROUND(100 * SUM(terminal_status = 'COMPLETE') / NULLIF(COUNT(*), 0), 1) AS success_rate,
                ROUND(AVG(CASE WHEN terminal_status = 'COMPLETE' THEN move_count END), 1) AS average_move_count,
                ROUND(AVG(CASE WHEN terminal_status = 'COMPLETE' THEN solve_duration_seconds END), 3) AS average_solve_time
         FROM solve_runs"
    )->fetch() ?: $summary;
    $recent = $pdo->query(
        "SELECT session_id, finished_at, terminal_status, move_count, solve_duration_seconds
         FROM solve_runs ORDER BY finished_at DESC LIMIT 25"
    )->fetchAll();
    $errors = $pdo->query(
        "SELECT session_id, finished_at, error_message FROM solve_runs
         WHERE terminal_status = 'ERROR' ORDER BY finished_at DESC LIMIT 10"
    )->fetchAll();
} catch (Throwable) {
    $configurationError = 'Dashboard data is unavailable. Check server configuration.';
}
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Rubik's Cube Solve Dashboard</title>
    <style>
        :root { color-scheme: dark; font-family: system-ui, sans-serif; }
        body { margin: 0; background: #10131a; color: #f4f6fb; }
        main { width: min(1100px, calc(100% - 2rem)); margin: 2rem auto; }
        h1, h2 { margin-bottom: .5rem; }
        .muted { color: #aab3c5; }
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin: 1.5rem 0; }
        .card, .panel { background: #1a2030; border: 1px solid #303a50; border-radius: 12px; padding: 1rem; }
        .value { display: block; font-size: 1.8rem; font-weight: 700; margin-top: .35rem; }
        .table-wrap { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: .7rem; text-align: left; border-bottom: 1px solid #303a50; white-space: nowrap; }
        th { color: #aab3c5; }
        .error { color: #ffb4b4; }
        @media (max-width: 600px) { main { width: min(100% - 1rem, 1100px); margin: 1rem auto; } th, td { padding: .55rem; } }
    </style>
</head>
<body>
<main>
    <h1>Rubik's Cube Solve Dashboard</h1>
    <p class="muted">Read-only terminal summaries from the 3×3 assistant.</p>
    <?php if ($configurationError !== null): ?>
        <p class="panel error"><?= h($configurationError) ?></p>
    <?php endif; ?>
    <section class="cards" aria-label="Solve statistics">
        <div class="card">Total attempts<span class="value"><?= h($summary['total_attempts']) ?></span></div>
        <div class="card">Completed solves<span class="value"><?= h($summary['completed_solves']) ?></span></div>
        <div class="card">Success rate<span class="value"><?= h($summary['success_rate'] ?? 0) ?>%</span></div>
        <div class="card">Average moves<span class="value"><?= h($summary['average_move_count'] ?? '—') ?></span></div>
        <div class="card">Average solve time<span class="value"><?= h($summary['average_solve_time'] ?? '—') ?> s</span></div>
    </section>
    <section class="panel">
        <h2>Recent sessions</h2>
        <div class="table-wrap"><table>
            <thead><tr><th>Finished (UTC)</th><th>Session</th><th>Status</th><th>Moves</th><th>Solve time</th></tr></thead>
            <tbody>
            <?php foreach ($recent as $row): ?>
                <tr><td><?= h($row['finished_at']) ?></td><td><?= h($row['session_id']) ?></td><td><?= h($row['terminal_status']) ?></td><td><?= h($row['move_count']) ?></td><td><?= h($row['solve_duration_seconds'] ?? '—') ?></td></tr>
            <?php endforeach; ?>
            </tbody>
        </table></div>
    </section>
    <section class="panel" style="margin-top: 1rem">
        <h2>Recent errors</h2>
        <?php if ($errors === []): ?><p class="muted">No errors recorded.</p><?php endif; ?>
        <?php foreach ($errors as $row): ?>
            <p><strong><?= h($row['finished_at']) ?></strong> · <?= h($row['session_id']) ?><br><span class="error"><?= h($row['error_message'] ?? 'No message') ?></span></p>
        <?php endforeach; ?>
    </section>
</main>
</body>
</html>
