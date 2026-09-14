import { useEffect, useState } from 'react';
import { fetchAppVersion } from '@/services/appInfo';

export function useAppVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchAppVersion().then((v) => {
      if (alive) setVersion(v);
    });
    return () => {
      alive = false;
    };
  }, []);

  return version;
}

export default useAppVersion;
