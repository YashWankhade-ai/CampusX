
document.addEventListener('alpine:init', () => {
    Alpine.store('theme', {
        mode: localStorage.getItem('theme') || 'light',
        toggle() {
            this.mode = this.mode === 'light' ? 'dark' : 'light';
            localStorage.setItem('theme', this.mode);
            document.documentElement.setAttribute('data-theme', this.mode);
        }
    });
});
