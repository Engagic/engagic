import { browser } from "$app/environment";

const getUserAgent = (): string => {
    if (!browser) return "";
    return navigator.userAgent;
};

const getIsMobile = (): boolean => {
    if (!browser) return false;
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(getUserAgent());
};

const getPreferences = () => {
    if (!browser) {
        return {
            reducedMotion: false,
            reducedTransparency: false,
        };
    }

    return {
        reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        reducedTransparency: window.matchMedia('(prefers-reduced-transparency: reduce)').matches,
    };
};

export const device = {
    is: {
        mobile: getIsMobile(),
        iPhone: browser && /iPhone/i.test(getUserAgent()),
    },
    browser: {
        chrome: browser && /Chrome/i.test(getUserAgent()),
    },
    prefers: getPreferences(),
};

export const app = {
    is: {
        installed: browser && window.matchMedia('(display-mode: standalone)').matches,
    },
};