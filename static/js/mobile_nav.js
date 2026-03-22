/* ── MOBILE NAV HAMBURGER ──
   Add this script to the bottom of every HTML page (before </body>)
   OR paste it at the bottom of script.js
*/

(function () {
    function initMobileNav() {
        var nav = document.querySelector('header nav');
        var header = document.querySelector('header');
        if (!nav || !header) return;

        /* Create hamburger button */
        var btn = document.createElement('button');
        btn.className = 'hamburger';
        btn.setAttribute('aria-label', 'Toggle menu');
        btn.innerHTML = '<span></span><span></span><span></span>';
        header.appendChild(btn);

        /* Create overlay */
        var overlay = document.createElement('div');
        overlay.className = 'nav-overlay';
        document.body.appendChild(overlay);

        function openNav() {
            nav.classList.add('open');
            btn.classList.add('open');
            overlay.classList.add('open');
            document.body.style.overflow = 'hidden';
        }

        function closeNav() {
            nav.classList.remove('open');
            btn.classList.remove('open');
            overlay.classList.remove('open');
            document.body.style.overflow = '';
        }

        btn.addEventListener('click', function () {
            nav.classList.contains('open') ? closeNav() : openNav();
        });

        overlay.addEventListener('click', closeNav);

        /* Close nav when a link is clicked */
        nav.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', closeNav);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobileNav);
    } else {
        initMobileNav();
    }
})();