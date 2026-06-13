// Theme Toggle Functionality

class ThemeManager {
    constructor() {
        this.theme = localStorage.getItem('theme') || 'dark';
        this.init();
    }

    init() {
        // Apply saved theme
        this.applyTheme(this.theme);
        
        // Create toggle button
        this.createToggleButton();
        
        // Listen for storage changes (sync across tabs)
        window.addEventListener('storage', (e) => {
            if (e.key === 'theme') {
                this.theme = e.newValue || 'dark';
                this.applyTheme(this.theme);
                this.updateToggleButton();
            }
        });
    }

    createToggleButton() {
        // Check if button already exists
        if (document.querySelector('.theme-toggle')) return;

        const toggle = document.createElement('div');
        toggle.className = 'theme-toggle';
        toggle.setAttribute('role', 'button');
        toggle.setAttribute('aria-label', 'Toggle theme');
        toggle.setAttribute('tabindex', '0');
        
        toggle.innerHTML = `
            <span class="theme-toggle-label">${this.theme === 'dark' ? 'Dark' : 'Light'}</span>
            <div class="theme-toggle-track">
                <div class="theme-toggle-thumb">
                    <i class="fas fa-${this.theme === 'dark' ? 'moon' : 'sun'}"></i>
                </div>
            </div>
        `;
        
        toggle.addEventListener('click', () => this.toggleTheme());
        toggle.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
        
        document.body.appendChild(toggle);
    }

    toggleTheme() {
        this.theme = this.theme === 'dark' ? 'light' : 'dark';
        this.applyTheme(this.theme);
        this.updateToggleButton();
        localStorage.setItem('theme', this.theme);
        
        // Dispatch event for other components
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: this.theme } }));
    }

    applyTheme(theme) {
        document.body.setAttribute('data-theme', theme);
        
        // Update meta theme-color for mobile browsers
        let metaTheme = document.querySelector('meta[name="theme-color"]');
        if (!metaTheme) {
            metaTheme = document.createElement('meta');
            metaTheme.name = 'theme-color';
            document.head.appendChild(metaTheme);
        }
        metaTheme.content = theme === 'dark' ? '#0B1120' : '#F8FAFC';
    }

    updateToggleButton() {
        const toggle = document.querySelector('.theme-toggle');
        if (!toggle) return;

        const label = toggle.querySelector('.theme-toggle-label');
        const icon = toggle.querySelector('.theme-toggle-thumb i');
        
        if (label) {
            label.textContent = this.theme === 'dark' ? 'Dark' : 'Light';
        }
        
        if (icon) {
            icon.className = `fas fa-${this.theme === 'dark' ? 'moon' : 'sun'}`;
        }
    }

    getTheme() {
        return this.theme;
    }
}

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeManager;
}
