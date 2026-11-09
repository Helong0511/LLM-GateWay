"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { infoFlash, type FlashMessage } from "@/components/ui/flash";

/**
 * 首屏/刷新加载提示：文案随语言切换更新；业务 setFlash 后不再被覆盖。
 */
export function useBootFlash(loadingText: string) {
  const booting = useRef(true);
  const [flash, setFlashState] = useState<FlashMessage | null>(() => infoFlash(loadingText));

  useEffect(() => {
    if (booting.current) {
      setFlashState(infoFlash(loadingText));
    }
  }, [loadingText]);

  const setFlash = useCallback((next: FlashMessage | null) => {
    booting.current = false;
    setFlashState(next);
  }, []);

  const startBoot = useCallback(() => {
    booting.current = true;
    setFlashState(infoFlash(loadingText));
  }, [loadingText]);

  return { flash, setFlash, startBoot };
}
