(() => {
    const feature = document.body.dataset.feature;
    if (!feature) return;

    function record() {
        if (document.visibilityState !== 'visible') return;
        fetch('/api/artifact-spirit/visit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({feature}),
            keepalive: true,
        }).then(response => {
            if (feature === 'artifact-spirit' && response.ok) {
                window.dispatchEvent(new Event('artifact-spirit-visit-recorded'));
            }
        }).catch(() => {});
    }

    window.addEventListener('pageshow', record);
    // A page opened into a background tab counts when first shown.
    if (document.visibilityState === 'hidden') {
        document.addEventListener('visibilitychange', record, {once: true});
    }
})();
