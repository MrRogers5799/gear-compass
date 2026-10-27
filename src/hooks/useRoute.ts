import { useEffect, useState } from 'react';

/** Hash routing (#/rankings, #/content/vorkath ...): no server config needed on GitHub Pages. */
export function useRoute(): string[] {
  const parse = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => { setRoute(parse()); window.scrollTo(0, 0); };
    addEventListener('hashchange', on);
    return () => removeEventListener('hashchange', on);
  }, []);
  return route;
}

export const navigate = (...parts: string[]) => {
  location.hash = '/' + parts.map(encodeURIComponent).join('/');
};
