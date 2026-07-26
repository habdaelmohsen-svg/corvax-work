import {create} from 'zustand';

type DashboardUiState = {
  menuOpen: boolean;
  darkMode: boolean;
  setMenuOpen: (open: boolean) => void;
  toggleTheme: () => void;
};

export const useDashboardUi = create<DashboardUiState>((set) => ({
  menuOpen: false,
  darkMode: localStorage.getItem('corvax_theme') === 'dark',
  setMenuOpen: (menuOpen) => set({menuOpen}),
  toggleTheme: () => set((state) => {
    const darkMode = !state.darkMode;
    localStorage.setItem('corvax_theme', darkMode ? 'dark' : 'light');
    return {darkMode};
  }),
}));
