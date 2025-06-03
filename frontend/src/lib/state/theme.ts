import { browser } from "$app/environment";
import { writable } from "svelte/store";

type Theme = "light" | "dark" | "auto";

const getSystemTheme = (): "light" | "dark" => {
    if (!browser) return "light";
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light";
};

const getStoredTheme = (): Theme => {
    if (!browser) return "auto";
    const stored = localStorage.getItem("engagemint-theme");
    if (stored && ["light", "dark", "auto"].includes(stored)) {
        return stored as Theme;
    }
    return "auto";
};

const resolveTheme = (theme: Theme): "light" | "dark" => {
    if (theme === "auto") {
        return getSystemTheme();
    }
    return theme;
};

const createThemeStore = () => {
    const { subscribe, set, update } = writable<"light" | "dark">(
        resolveTheme(getStoredTheme())
    );

    return {
        subscribe,
        set: (theme: Theme) => {
            if (browser) {
                localStorage.setItem("engagemint-theme", theme);
            }
            set(resolveTheme(theme));
        },
        toggle: () => {
            update(current => {
                const newTheme = current === "light" ? "dark" : "light";
                if (browser) {
                    localStorage.setItem("engagemint-theme", newTheme);
                }
                return newTheme;
            });
        }
    };
};

export default createThemeStore();

export const statusBarColors = {
    mobile: {
        light: "#f4f4f4",
        dark: "#131313",
    },
    desktop: {
        light: "#ffffff",
        dark: "#000000",
    },
};