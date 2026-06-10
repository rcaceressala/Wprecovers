#!/bin/bash
#
# espaciosunicos-fixes.sh
# WP-CLI repair script for espaciosunicos.cl — addresses the 11 issues
# found by the WPRecover audit.
#
# -----------------------------------------------------------------------
# USAGE
#   ./espaciosunicos-fixes.sh apply [N|all]
#   ./espaciosunicos-fixes.sh rollback [N|all]
#
#   apply all        Apply all 11 fixes, in order
#   apply 7          Apply only fix #7
#   rollback all      Undo all fixes, in reverse order
#   rollback 7        Undo only fix #7
#
# REQUIREMENTS
#   - Run from the WordPress root directory (where wp-config.php lives)
#   - WP-CLI installed and on PATH
#   - WPRecover M4 policy: run on STAGING first. Do not run directly
#     against production until validated on staging.
#
# HOW IT WORKS
#   - Fixes 1, 5, 6, 10 append marker-delimited PHP blocks to the active
#     theme's functions.php ("// === WPRECOVER FIX: N_name START/END ===").
#   - Fixes 2 and 9 add marker-delimited blocks to .htaccess
#     ("# === WPRECOVER FIX: N_name START/END ===").
#   - Fixes 3, 4, 7, 8, 11 change wp_options / post data via WP-CLI and
#     `wp eval-file`, saving the previous state under ./wprecover-fix-state/
#     so rollback can restore it exactly.
#   - rollback removes the marker blocks / restores saved state.
# -----------------------------------------------------------------------

set -euo pipefail

STATE_DIR="./wprecover-fix-state"
mkdir -p "$STATE_DIR"

if ! command -v wp >/dev/null 2>&1; then
  echo "ERROR: WP-CLI ('wp') not found on PATH." >&2
  exit 1
fi

if [ ! -f "./wp-config.php" ]; then
  echo "ERROR: wp-config.php not found. Run this script from the WordPress root." >&2
  exit 1
fi

THEME_DIR="$(wp theme path)"
FUNCTIONS_PHP="$THEME_DIR/functions.php"
ABSPATH="$(wp eval 'echo rtrim(ABSPATH, "/");')"
HTACCESS="$ABSPATH/.htaccess"
[ -f "$HTACCESS" ] || touch "$HTACCESS"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Append a PHP block to $1, reading the PHP code from stdin.
# Skips if the marker is already present (idempotent).
append_php_block() {  # file marker
  local file="$1" marker="$2"
  if grep -q "WPRECOVER FIX: $marker START" "$file" 2>/dev/null; then
    cat >/dev/null
    echo "  [skip] $marker already present in $(basename "$file")"
    return 0
  fi
  {
    echo ""
    echo "// === WPRECOVER FIX: $marker START ==="
    cat
    echo "// === WPRECOVER FIX: $marker END ==="
  } >> "$file"
  echo "  [ok] appended $marker to $(basename "$file")"
}

# Append a block to .htaccess, reading the content from stdin.
append_htaccess_block() {  # marker
  local marker="$1"
  if grep -q "WPRECOVER FIX: $marker START" "$HTACCESS" 2>/dev/null; then
    cat >/dev/null
    echo "  [skip] $marker already present in .htaccess"
    return 0
  fi
  cp "$HTACCESS" "$STATE_DIR/.htaccess.bak.$marker"
  {
    echo ""
    echo "# === WPRECOVER FIX: $marker START ==="
    cat
    echo "# === WPRECOVER FIX: $marker END ==="
  } >> "$HTACCESS"
  echo "  [ok] appended $marker to .htaccess"
}

# Prepend a block to .htaccess (must run before WordPress's rewrite rules).
prepend_htaccess_block() {  # marker
  local marker="$1"
  if grep -q "WPRECOVER FIX: $marker START" "$HTACCESS" 2>/dev/null; then
    cat >/dev/null
    echo "  [skip] $marker already present in .htaccess"
    return 0
  fi
  cp "$HTACCESS" "$STATE_DIR/.htaccess.bak.$marker"
  local tmp; tmp="$STATE_DIR/.htaccess.new"
  {
    echo "# === WPRECOVER FIX: $marker START ==="
    cat
    echo "# === WPRECOVER FIX: $marker END ==="
    echo ""
    cat "$HTACCESS"
  } > "$tmp"
  mv "$tmp" "$HTACCESS"
  echo "  [ok] prepended $marker to .htaccess"
}

# Remove a marker-delimited block from any file (functions.php or .htaccess).
remove_block() {  # file marker
  local file="$1" marker="$2"
  if ! grep -q "WPRECOVER FIX: $marker START" "$file" 2>/dev/null; then
    echo "  [skip] $marker not found in $(basename "$file")"
    return 0
  fi
  sed -i.bak "/WPRECOVER FIX: ${marker} START/,/WPRECOVER FIX: ${marker} END/d" "$file"
  rm -f "${file}.bak"
  echo "  [ok] removed $marker from $(basename "$file")"
}

# ---------------------------------------------------------------------------
# Fix 1 — Remove WordPress version from meta generator tag
# ---------------------------------------------------------------------------
fix_1() {
  echo "[1/11] Removing WordPress version from meta generator tag..."
  append_php_block "$FUNCTIONS_PHP" "1_meta_generator" <<'PHP'
add_filter('the_generator', '__return_empty_string');
PHP
}
rollback_1() {
  echo "[1/11] Rollback: restoring meta generator tag..."
  remove_block "$FUNCTIONS_PHP" "1_meta_generator"
}

# ---------------------------------------------------------------------------
# Fix 2 — Add security headers via .htaccess
# ---------------------------------------------------------------------------
fix_2() {
  echo "[2/11] Adding security headers to .htaccess..."
  append_htaccess_block "2_security_headers" <<'HTACCESS'
<IfModule mod_headers.c>
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-XSS-Protection "1; mode=block"
    Header always set X-Content-Type-Options "nosniff"
</IfModule>
HTACCESS
}
rollback_2() {
  echo "[2/11] Rollback: removing security headers from .htaccess..."
  remove_block "$HTACCESS" "2_security_headers"
}

# ---------------------------------------------------------------------------
# Fix 3 — Enable XML sitemap via Rank Math
# ---------------------------------------------------------------------------
fix_3() {
  echo "[3/11] Enabling XML sitemap via Rank Math..."
  if ! wp plugin is-active seo-by-rank-math >/dev/null 2>&1; then
    wp plugin activate seo-by-rank-math
  fi
  cat > "$STATE_DIR/fix3.php" <<'PHP'
<?php
$modules = (array) get_option('rank-math-modules', []);
if (!in_array('sitemap', $modules, true)) {
    file_put_contents(__DIR__ . '/fix3_modules_before.json', json_encode($modules));
    $modules[] = 'sitemap';
    update_option('rank-math-modules', $modules);
    WP_CLI::log('sitemap module enabled');
} else {
    WP_CLI::log('sitemap module already enabled');
}
PHP
  wp eval-file "$STATE_DIR/fix3.php"
  wp rewrite flush
  echo "  Sitemap should now be available at /sitemap_index.xml"
}
rollback_3() {
  echo "[3/11] Rollback: disabling Rank Math sitemap module..."
  if [ ! -f "$STATE_DIR/fix3_modules_before.json" ]; then
    echo "  [skip] no prior module list recorded"
    return 0
  fi
  cat > "$STATE_DIR/fix3_rollback.php" <<'PHP'
<?php
$before = json_decode(file_get_contents(__DIR__ . '/fix3_modules_before.json'), true);
update_option('rank-math-modules', $before);
WP_CLI::log('restored previous Rank Math module list');
PHP
  wp eval-file "$STATE_DIR/fix3_rollback.php"
  rm -f "$STATE_DIR/fix3_modules_before.json" "$STATE_DIR/fix3_rollback.php" "$STATE_DIR/fix3.php"
  wp rewrite flush
}

# ---------------------------------------------------------------------------
# Fix 4 — Fix robots.txt to allow Googlebot
# ---------------------------------------------------------------------------
fix_4() {
  echo "[4/11] Allowing Googlebot in robots.txt..."
  wp option get blog_public > "$STATE_DIR/fix4_blog_public_before.txt"
  wp option update blog_public 1
  wp rewrite flush

  local phys_robots="$ABSPATH/robots.txt"
  if [ -f "$phys_robots" ]; then
    cp "$phys_robots" "$STATE_DIR/robots.txt.bak"
    sed -i.orig '/^Disallow:[[:space:]]*\/[[:space:]]*$/d' "$phys_robots"
    rm -f "${phys_robots}.orig"
    echo "  [ok] removed blanket 'Disallow: /' from physical robots.txt"
  else
    echo "  [info] no physical robots.txt found - virtual robots.txt now allows indexing"
  fi
}
rollback_4() {
  echo "[4/11] Rollback: restoring previous indexing settings..."
  if [ -f "$STATE_DIR/fix4_blog_public_before.txt" ]; then
    wp option update blog_public "$(cat "$STATE_DIR/fix4_blog_public_before.txt")"
    rm -f "$STATE_DIR/fix4_blog_public_before.txt"
  fi
  if [ -f "$STATE_DIR/robots.txt.bak" ]; then
    cp "$STATE_DIR/robots.txt.bak" "$ABSPATH/robots.txt"
    rm -f "$STATE_DIR/robots.txt.bak"
  fi
  wp rewrite flush
}

# ---------------------------------------------------------------------------
# Fix 5 — Add clickable phone number filter (tel: links)
# ---------------------------------------------------------------------------
fix_5() {
  echo "[5/11] Wrapping phone numbers in clickable tel: links..."
  append_php_block "$FUNCTIONS_PHP" "5_tel_clickable" <<'PHP'
add_filter('the_content', 'wpr_wrap_phones');
function wpr_wrap_phones($content) {
    return preg_replace(
        '/\b(\+?[\d][\d\s\-\.\(\)]{7,})/',
        '<a href="tel:$1">$1</a>',
        $content
    );
}
PHP
}
rollback_5() {
  echo "[5/11] Rollback: removing tel: link filter..."
  remove_block "$FUNCTIONS_PHP" "5_tel_clickable"
}

# ---------------------------------------------------------------------------
# Fix 6 — Configure Google Analytics (placeholder Measurement ID)
# ---------------------------------------------------------------------------
fix_6() {
  echo "[6/11] Adding Google Analytics (GA4) snippet..."
  echo "  NOTE: replace G-XXXXXXXXXX with the real Measurement ID before going live."
  append_php_block "$FUNCTIONS_PHP" "6_google_analytics" <<'PHP'
add_action('wp_head', function () {
    ?>
    <!-- Google tag (gtag.js) - WPRecover placeholder, replace G-XXXXXXXXXX -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-XXXXXXXXXX');
    </script>
    <?php
});
PHP
}
rollback_6() {
  echo "[6/11] Rollback: removing Google Analytics snippet..."
  remove_block "$FUNCTIONS_PHP" "6_google_analytics"
}

# ---------------------------------------------------------------------------
# Fix 7 — Remove (unpublish) WooCommerce products without a price
# ---------------------------------------------------------------------------
fix_7() {
  echo "[7/11] Setting WooCommerce products without a price to draft..."
  cat > "$STATE_DIR/fix7.php" <<'PHP'
<?php
$ids = get_posts([
    'post_type'   => 'product',
    'post_status' => 'publish',
    'numberposts' => -1,
    'fields'      => 'ids',
    'meta_query'  => [
        'relation' => 'OR',
        ['key' => '_price', 'value' => '', 'compare' => '='],
        ['key' => '_price', 'compare' => 'NOT EXISTS'],
    ],
]);
file_put_contents(__DIR__ . '/fix7_product_ids.txt', implode("\n", $ids));
foreach ($ids as $id) {
    wp_update_post(['ID' => $id, 'post_status' => 'draft']);
}
WP_CLI::log(count($ids) . ' product(s) without a price set to draft.');
PHP
  wp eval-file "$STATE_DIR/fix7.php"
}
rollback_7() {
  echo "[7/11] Rollback: restoring products without price to 'publish'..."
  local id_file="$STATE_DIR/fix7_product_ids.txt"
  if [ ! -s "$id_file" ]; then
    echo "  [skip] no product IDs recorded"
    return 0
  fi
  while read -r id; do
    [ -n "$id" ] && wp post update "$id" --post_status=publish
  done < "$id_file"
  rm -f "$id_file" "$STATE_DIR/fix7.php"
}

# ---------------------------------------------------------------------------
# Fix 8 — Fix duplicate post/page slugs
# ---------------------------------------------------------------------------
fix_8() {
  echo "[8/11] Fixing duplicate post/page slugs..."
  cat > "$STATE_DIR/fix8.php" <<'PHP'
<?php
global $wpdb;
$dupes = $wpdb->get_results("
    SELECT post_name, GROUP_CONCAT(ID ORDER BY ID) AS ids
    FROM {$wpdb->posts}
    WHERE post_status = 'publish' AND post_type IN ('post','page')
    GROUP BY post_name
    HAVING COUNT(*) > 1
");
$log = fopen(__DIR__ . '/fix8_slug_map.csv', 'w');
foreach ($dupes as $d) {
    $ids = explode(',', $d->ids);
    array_shift($ids); // keep the oldest post with the original slug
    foreach ($ids as $id) {
        $new_slug = sanitize_title($d->post_name . '-' . $id);
        fputcsv($log, [$id, $d->post_name, $new_slug]);
        wp_update_post(['ID' => (int) $id, 'post_name' => $new_slug]);
        WP_CLI::log("Post $id: '{$d->post_name}' -> '$new_slug'");
    }
}
fclose($log);
PHP
  wp eval-file "$STATE_DIR/fix8.php"
  wp rewrite flush
}
rollback_8() {
  echo "[8/11] Rollback: restoring original slugs..."
  local map_file="$STATE_DIR/fix8_slug_map.csv"
  if [ ! -s "$map_file" ]; then
    echo "  [skip] no slug changes recorded"
    return 0
  fi
  while IFS=, read -r id old_slug new_slug; do
    [ -n "$id" ] && wp post update "$id" --post_name="$old_slug"
  done < "$map_file"
  rm -f "$map_file" "$STATE_DIR/fix8.php"
  wp rewrite flush
}

# ---------------------------------------------------------------------------
# Fix 9 — Add SSL redirect in .htaccess
# ---------------------------------------------------------------------------
fix_9() {
  echo "[9/11] Adding SSL redirect to .htaccess..."
  prepend_htaccess_block "9_ssl_redirect" <<'HTACCESS'
<IfModule mod_rewrite.c>
RewriteEngine On
RewriteCond %{HTTPS} off
RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]
</IfModule>
HTACCESS

  local current_siteurl current_home
  current_siteurl="$(wp option get siteurl)"
  current_home="$(wp option get home)"
  if [[ "$current_siteurl" == http://* ]]; then
    echo "$current_siteurl" > "$STATE_DIR/fix9_siteurl_before.txt"
    echo "$current_home" > "$STATE_DIR/fix9_home_before.txt"
    wp option update siteurl "${current_siteurl/http:/https:}"
    wp option update home "${current_home/http:/https:}"
    echo "  [ok] updated siteurl/home to https://"
  else
    echo "  [skip] siteurl already uses https://"
  fi
}
rollback_9() {
  echo "[9/11] Rollback: removing SSL redirect from .htaccess..."
  remove_block "$HTACCESS" "9_ssl_redirect"
  if [ -f "$STATE_DIR/fix9_siteurl_before.txt" ]; then
    wp option update siteurl "$(cat "$STATE_DIR/fix9_siteurl_before.txt")"
    wp option update home "$(cat "$STATE_DIR/fix9_home_before.txt")"
    rm -f "$STATE_DIR/fix9_siteurl_before.txt" "$STATE_DIR/fix9_home_before.txt"
  fi
}

# ---------------------------------------------------------------------------
# Fix 10 — Add WhatsApp floating button (placeholder phone number)
# ---------------------------------------------------------------------------
fix_10() {
  echo "[10/11] Adding WhatsApp floating button..."
  echo "  NOTE: replace 56900000000 with the real WhatsApp number (country code, no '+' or spaces)."
  append_php_block "$FUNCTIONS_PHP" "10_whatsapp_button" <<'PHP'
add_action('wp_footer', 'wpr_whatsapp_btn');
function wpr_whatsapp_btn() {
    $phone = '56900000000'; // WPRecover placeholder - replace with real number
    echo '<a href="https://wa.me/' . esc_attr($phone) . '" target="_blank" rel="noopener"
        style="position:fixed;bottom:80px;right:20px;z-index:9999;">
        <img src="https://cdn.simpleicons.org/whatsapp/25D366" width="50" alt="WhatsApp"/></a>';
}
PHP
}
rollback_10() {
  echo "[10/11] Rollback: removing WhatsApp button..."
  remove_block "$FUNCTIONS_PHP" "10_whatsapp_button"
}

# ---------------------------------------------------------------------------
# Fix 11 — Set meta description via wp_options
# ---------------------------------------------------------------------------
fix_11() {
  echo "[11/11] Setting homepage meta description..."
  echo "  NOTE: edit the placeholder text in fix11.php / state file before relying on it long-term."
  cat > "$STATE_DIR/fix11.php" <<'PHP'
<?php
$desc = 'Espacios Unicos: [EDITAR] descripcion de 150-160 caracteres con palabras clave del negocio y ubicacion.';
$active_plugins = (array) get_option('active_plugins', []);
$rank_math_active = in_array('seo-by-rank-math/rank-math.php', $active_plugins, true);

if ($rank_math_active) {
    $titles = get_option('rank-math-options-titles', []);
    file_put_contents(__DIR__ . '/fix11_before.json', json_encode([
        'plugin' => 'rank-math',
        'value'  => $titles['homepage_description'] ?? '',
    ]));
    $titles['homepage_description'] = $desc;
    update_option('rank-math-options-titles', $titles);
    WP_CLI::log('Updated Rank Math homepage_description');
} else {
    file_put_contents(__DIR__ . '/fix11_before.json', json_encode([
        'plugin' => 'core',
        'value'  => get_option('blogdescription'),
    ]));
    update_option('blogdescription', $desc);
    WP_CLI::log('Rank Math not active - updated tagline (blogdescription) as fallback');
}
PHP
  wp eval-file "$STATE_DIR/fix11.php"
}
rollback_11() {
  echo "[11/11] Rollback: restoring previous meta description..."
  if [ ! -f "$STATE_DIR/fix11_before.json" ]; then
    echo "  [skip] no prior value recorded"
    return 0
  fi
  cat > "$STATE_DIR/fix11_rollback.php" <<'PHP'
<?php
$before = json_decode(file_get_contents(__DIR__ . '/fix11_before.json'), true);
if (($before['plugin'] ?? '') === 'rank-math') {
    $titles = get_option('rank-math-options-titles', []);
    $titles['homepage_description'] = $before['value'];
    update_option('rank-math-options-titles', $titles);
} else {
    update_option('blogdescription', $before['value']);
}
WP_CLI::log('Restored previous meta description');
PHP
  wp eval-file "$STATE_DIR/fix11_rollback.php"
  rm -f "$STATE_DIR/fix11_before.json" "$STATE_DIR/fix11_rollback.php" "$STATE_DIR/fix11.php"
}

# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------
ALL_FIXES=(1 2 3 4 5 6 7 8 9 10 11)

usage() {
  cat <<USAGE
Usage: $0 apply|rollback [N|all]

  apply all        Apply all 11 fixes, in order
  apply N          Apply only fix #N (1-11)
  rollback all     Undo all fixes, in reverse order
  rollback N       Undo only fix #N (1-11)

Examples:
  $0 apply all
  $0 apply 7
  $0 rollback 9
  $0 rollback all
USAGE
  exit 1
}

[ $# -ge 1 ] || usage
ACTION="$1"
TARGET="${2:-all}"

case "$ACTION" in
  apply)
    if [ "$TARGET" = "all" ]; then
      for n in "${ALL_FIXES[@]}"; do "fix_$n"; done
    else
      "fix_$TARGET"
    fi
    ;;
  rollback)
    if [ "$TARGET" = "all" ]; then
      for ((i=${#ALL_FIXES[@]}-1; i>=0; i--)); do "rollback_${ALL_FIXES[i]}"; done
    else
      "rollback_$TARGET"
    fi
    ;;
  *)
    usage
    ;;
esac

echo ""
echo "Done. Run 'wp cache flush' and clear any page-cache plugin / CDN cache to see changes."
