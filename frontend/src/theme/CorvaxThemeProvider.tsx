import {useMemo, type ReactNode} from 'react';
import {CacheProvider} from '@emotion/react';
import createCache from '@emotion/cache';
import {CssBaseline, ThemeProvider, createTheme} from '@mui/material';
import rtlPlugin from '@mui/stylis-plugin-rtl';
import {prefixer} from 'stylis';
import {useDashboardUi} from '../dashboard/store';

type Lang = 'ar' | 'en';

const ltrCache = createCache({key: 'corvax-ltr'});
const rtlCache = createCache({key: 'corvax-rtl', stylisPlugins: [prefixer, rtlPlugin]});

export function CorvaxThemeProvider({lang, children}: {lang: Lang; children: ReactNode}) {
  const darkMode = useDashboardUi((state) => state.darkMode);
  const direction = lang === 'ar' ? 'rtl' : 'ltr';
  const theme = useMemo(() => createTheme({
    direction,
    cssVariables: true,
    palette: {
      mode: darkMode ? 'dark' : 'light',
      primary: {main: '#175cd3', light: '#4f8df7', dark: '#0b3b91', contrastText: '#ffffff'},
      secondary: {main: '#c98b2b', light: '#efc46f', dark: '#81530f', contrastText: '#ffffff'},
      success: {main: '#16875b'},
      warning: {main: '#c9770c'},
      error: {main: '#c53b49'},
      info: {main: '#176baf'},
      background: darkMode
        ? {default: '#07111f', paper: '#0e1b2b'}
        : {default: '#f3f6fb', paper: '#ffffff'},
      text: darkMode
        ? {primary: '#eef5ff', secondary: '#9eb0c5'}
        : {primary: '#12243a', secondary: '#62748a'},
      divider: darkMode ? 'rgba(159, 181, 207, .16)' : '#dce5ef',
    },
    shape: {borderRadius: 14},
    typography: {
      fontFamily: 'Alexandria, Inter, "Segoe UI", Tahoma, Arial, sans-serif',
      button: {fontWeight: 700, textTransform: 'none'},
      h1: {fontWeight: 800, letterSpacing: '-.035em'},
      h2: {fontWeight: 800, letterSpacing: '-.025em'},
      h3: {fontWeight: 750, letterSpacing: '-.015em'},
      body1: {lineHeight: 1.65},
      body2: {lineHeight: 1.6},
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          html: {colorScheme: darkMode ? 'dark' : 'light'},
          body: {minWidth: 320, margin: 0},
          '::selection': {background: 'rgba(23, 92, 211, .2)'},
        },
      },
      MuiButtonBase: {defaultProps: {disableRipple: false}},
      MuiButton: {
        defaultProps: {disableElevation: true},
        styleOverrides: {root: {minHeight: 42, borderRadius: 12, paddingInline: 18}},
      },
      MuiPaper: {
        defaultProps: {elevation: 0},
        styleOverrides: {
          root: {
            backgroundImage: 'none',
            border: `1px solid ${darkMode ? 'rgba(159,181,207,.16)' : '#dce5ef'}`,
          },
        },
      },
      MuiChip: {styleOverrides: {root: {fontWeight: 700, borderRadius: 999}}},
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            minHeight: 44,
            borderRadius: 12,
            background: darkMode ? 'rgba(255,255,255,.035)' : '#f8fafd',
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          head: {fontWeight: 800, color: darkMode ? '#dceaff' : '#29435f'},
          root: {borderColor: darkMode ? 'rgba(159,181,207,.14)' : '#e3eaf2'},
        },
      },
      MuiTooltip: {styleOverrides: {tooltip: {borderRadius: 9, fontSize: 11}}},
    },
  }), [darkMode, direction]);

  return <CacheProvider value={direction === 'rtl' ? rtlCache : ltrCache}>
    <ThemeProvider theme={theme}>
      <CssBaseline/>
      {children}
    </ThemeProvider>
  </CacheProvider>;
}
