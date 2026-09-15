<?php
declare(strict_types=1);

session_start([
    'use_strict_mode' => true,
    'cookie_httponly' => true,
    'cookie_samesite' => 'Strict',
    'cookie_secure' => isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
]);
header('Cache-Control: no-store');
$_SESSION['csrf_token'] ??= bin2hex(random_bytes(32));

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
$actionError = null;
$notice = $_SESSION['notice'] ?? null;
unset($_SESSION['notice']);
$configuredKey = getenv('RUBIKS_API_KEY');
$keyFingerprint = is_string($configuredKey) && $configuredKey !== ''
    ? hash('sha256', $configuredKey) : null;
$canRemove = $keyFingerprint !== null
    && hash_equals($keyFingerprint, $_SESSION['remove_access'] ?? '');
$page = max(1, (int) (filter_input(INPUT_GET, 'page', FILTER_VALIDATE_INT) ?: 1));
$pageSize = 25;
$pageCount = 1;

if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST') {
    $csrf = $_POST['csrf_token'] ?? null;
    $action = $_POST['action'] ?? null;
    if (!is_string($csrf) || !hash_equals($_SESSION['csrf_token'], $csrf)) {
        http_response_code(403);
        $actionError = 'Request expired. Reload the page and try again.';
    } elseif ($action === 'unlock') {
        $providedKey = $_POST['api_key'] ?? null;
        if ($keyFingerprint !== null && is_string($providedKey)
            && hash_equals($configuredKey, $providedKey)) {
            session_regenerate_id(true);
            $_SESSION['remove_access'] = $keyFingerprint;
            $_SESSION['notice'] = 'Session removal enabled.';
            header('Location: index.php?page=' . $page, true, 303);
            exit;
        }
        http_response_code(403);
        $actionError = 'API key is incorrect or server authentication is not configured.';
    } elseif ($action === 'lock') {
        unset($_SESSION['remove_access']);
        header('Location: index.php?page=' . $page, true, 303);
        exit;
    } elseif ($action === 'delete') {
        $sessionId = $_POST['session_id'] ?? null;
        if (!$canRemove) {
            http_response_code(403);
            $actionError = 'Enter the API key to enable removal first.';
        } elseif (!is_string($sessionId) || !preg_match('/^[A-Za-z0-9-]{1,64}$/', $sessionId)) {
            http_response_code(400);
            $actionError = 'Invalid session ID.';
        }
    } else {
        http_response_code(400);
        $actionError = 'Unknown action.';
    }
}

try {
    if (!$database || !$username || $password === false) {
        throw new RuntimeException('Dashboard database access is not configured.');
    }
    $pdo = new PDO(
        "mysql:host={$host};port={$port};dbname={$database};charset=utf8mb4",
        $username,
        $password,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC]
    );
    if (($_SERVER['REQUEST_METHOD'] ?? '') === 'POST'
        && ($_POST['action'] ?? '') === 'delete' && $actionError === null) {
        try {
            $statement = $pdo->prepare('DELETE FROM solve_runs WHERE session_id = :session_id');
            $statement->execute(['session_id' => $sessionId]);
            $_SESSION['notice'] = $statement->rowCount() > 0
                ? 'Session removed from the server database.' : 'Session was already removed.';
            header('Location: index.php?page=' . $page, true, 303);
            exit;
        } catch (Throwable) {
            http_response_code(500);
            $actionError = 'Could not remove session. Check database access and DELETE permission.';
        }
    }
    $summary = $pdo->query(
        "SELECT COUNT(*) AS total_attempts,
                SUM(terminal_status = 'COMPLETE') AS completed_solves,
                ROUND(100 * SUM(terminal_status = 'COMPLETE') / NULLIF(COUNT(*), 0), 1) AS success_rate,
                ROUND(AVG(CASE WHEN terminal_status = 'COMPLETE' THEN move_count END), 1) AS average_move_count,
                ROUND(AVG(CASE WHEN terminal_status = 'COMPLETE' THEN solve_duration_seconds END), 3) AS average_solve_time
         FROM solve_runs"
    )->fetch() ?: $summary;
    $pageCount = max(1, (int) ceil((int) $summary['total_attempts'] / $pageSize));
    $page = min($page, $pageCount);
    $recentStatement = $pdo->prepare(
        "SELECT session_id, finished_at, terminal_status, move_count, solve_duration_seconds
         FROM solve_runs ORDER BY finished_at DESC, session_id DESC LIMIT :limit OFFSET :offset"
    );
    $recentStatement->bindValue(':limit', $pageSize, PDO::PARAM_INT);
    $recentStatement->bindValue(':offset', ($page - 1) * $pageSize, PDO::PARAM_INT);
    $recentStatement->execute();
    $recent = $recentStatement->fetchAll();
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
        .notice { color: #a5e5b1; }
        button, input { font: inherit; border-radius: 6px; padding: .5rem .75rem; }
        button { cursor: pointer; background: #303a50; color: #f4f6fb; border: 1px solid #53617c; }
        button.remove { color: #ffb4b4; border-color: #9a5360; }
        button:disabled { opacity: .45; cursor: default; }
        input { background: #10131a; color: #f4f6fb; border: 1px solid #53617c; max-width: 100%; box-sizing: border-box; }
        .management { margin: 1rem 0; }
        .management form { display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
        .pagination { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1rem; }
        a { color: #a7c8ff; }
        @media (max-width: 600px) { main { width: min(100% - 1rem, 1100px); margin: 1rem auto; } th, td { padding: .55rem; } }
    </style>
</head>
<body>
<main>
    <h1>Rubik's Cube Solve Dashboard</h1>
    <p class="muted">Solve history from the 3×3 assistant.</p>
    <?php if ($notice !== null): ?><p class="panel notice" role="status"><?= h($notice) ?></p><?php endif; ?>
    <?php if ($actionError !== null): ?><p class="panel error" role="alert"><?= h($actionError) ?></p><?php endif; ?>
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
    <section class="panel management" aria-label="Session management">
        <?php if (!$canRemove): ?>
            <form method="post" action="index.php?page=<?= h($page) ?>">
                <input type="hidden" name="action" value="unlock">
                <input type="hidden" name="csrf_token" value="<?= h($_SESSION['csrf_token']) ?>">
                <label for="api-key">API key</label>
                <input id="api-key" type="password" name="api_key" required autocomplete="off">
                <button type="submit">Enable removal</button>
            </form>
        <?php else: ?>
            <form method="post" action="index.php?page=<?= h($page) ?>">
                <input type="hidden" name="action" value="lock">
                <input type="hidden" name="csrf_token" value="<?= h($_SESSION['csrf_token']) ?>">
                <span>Session removal enabled.</span>
                <button type="submit">Disable removal</button>
            </form>
        <?php endif; ?>
        <p class="muted">Removal deletes the server record and updates statistics. Local scan files and Pi history are retained.</p>
    </section>
    <section class="panel">
        <h2>Recent sessions</h2>
        <div class="table-wrap"><table>
            <thead><tr><th>Finished (UTC)</th><th>Session</th><th>Status</th><th>Moves</th><th>Solve time</th><th>Actions</th></tr></thead>
            <tbody>
            <?php foreach ($recent as $row): ?>
                <tr><td><?= h($row['finished_at']) ?></td><td><?= h($row['session_id']) ?></td><td><?= h($row['terminal_status']) ?></td><td><?= h($row['move_count']) ?></td><td><?= h($row['solve_duration_seconds'] ?? '—') ?></td>
                    <td><form method="post" action="index.php?page=<?= h($page) ?>">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="csrf_token" value="<?= h($_SESSION['csrf_token']) ?>">
                        <input type="hidden" name="session_id" value="<?= h($row['session_id']) ?>">
                        <button class="remove" type="submit" aria-label="Remove session <?= h($row['session_id']) ?>" <?= !$canRemove ? 'disabled' : '' ?>>Remove</button>
                    </form></td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table></div>
        <?php if ($recent === []): ?><p class="muted">No sessions recorded.</p><?php endif; ?>
        <nav class="pagination" aria-label="Session pages">
            <?php if ($page > 1): ?><a href="index.php?page=<?= h($page - 1) ?>">Newer sessions</a><?php endif; ?>
            <span>Page <?= h($page) ?> of <?= h($pageCount) ?></span>
            <?php if ($page < $pageCount): ?><a href="index.php?page=<?= h($page + 1) ?>">Older sessions</a><?php endif; ?>
        </nav>
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
