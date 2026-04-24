import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Html5Qrcode } from 'html5-qrcode';
import { Camera, FileImage, Loader2, QrCode, X } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * DppScanner — modal dialog that scans an EU Digital Product Passport
 * QR code either from the device camera (primary) or an uploaded image
 * (fallback). On a successful decode it calls ``onDecoded(payload)`` with
 * the raw string so the parent decides what to do (call /import-dpp,
 * navigate, etc.).
 */
export const DppScanner = ({ open, onOpenChange, onDecoded }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState('camera'); // 'camera' | 'file'
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [fileBusy, setFileBusy] = useState(false);
  const readerId = 'dpp-qr-reader';
  const scannerRef = useRef(null);

  // ------------------ camera lifecycle ------------------
  useEffect(() => {
    if (!open || mode !== 'camera') return undefined;

    let active = true;
    let instance = null;
    setCameraError(null);
    setCameraReady(false);

    (async () => {
      try {
        // html5-qrcode needs the target div already in the DOM.
        await new Promise((r) => setTimeout(r, 40));
        if (!active) return;
        instance = new Html5Qrcode(readerId, { verbose: false });
        scannerRef.current = instance;
        const config = { fps: 10, qrbox: { width: 260, height: 260 }, aspectRatio: 1.0 };
        const cameras = await Html5Qrcode.getCameras();
        if (!cameras || cameras.length === 0) {
          setCameraError(t('dpp.scanner.noCamera'));
          return;
        }
        // Prefer rear camera when available (mobile).
        const rear =
          cameras.find((c) => /back|rear|environment/i.test(c.label)) ||
          cameras[cameras.length - 1];
        await instance.start(
          rear.id,
          config,
          (decodedText) => {
            if (!active) return;
            active = false;
            try {
              instance.stop().catch(() => {});
            } catch (_) { /* no-op */ }
            onDecoded(decodedText);
          },
          () => { /* per-frame scan failure — ignore, it's chatty */ },
        );
        if (active) setCameraReady(true);
      } catch (err) {
        const msg = err?.message || String(err);
        setCameraError(
          /permission|denied|notallowed/i.test(msg)
            ? t('dpp.scanner.permissionDenied')
            : msg || t('dpp.scanner.cameraFailed'),
        );
      }
    })();

    return () => {
      active = false;
      const inst = scannerRef.current;
      scannerRef.current = null;
      if (inst) {
        try {
          // stop returns a promise; ignore rejection if already stopped.
          inst.stop().catch(() => {}).finally(() => {
            try { inst.clear(); } catch (_) { /* ignore */ }
          });
        } catch (_) { /* ignore */ }
      }
    };
  }, [open, mode, onDecoded, t]);

  // ------------------ file upload path ------------------
  const handleFile = async (file) => {
    if (!file) return;
    setFileBusy(true);
    try {
      // html5-qrcode can decode a still image file directly.
      const tempId = 'dpp-qr-reader-file';
      const holder = document.getElementById(tempId) || document.createElement('div');
      holder.id = tempId;
      holder.style.display = 'none';
      if (!holder.parentElement) document.body.appendChild(holder);
      const scanner = new Html5Qrcode(tempId, { verbose: false });
      try {
        const result = await scanner.scanFile(file, /* showImage = */ false);
        onDecoded(result);
      } catch (err) {
        toast.error(t('dpp.scanner.noCodeInImage'));
      } finally {
        try { await scanner.clear(); } catch (_) { /* ignore */ }
        if (holder.parentElement) holder.parentElement.removeChild(holder);
      }
    } finally {
      setFileBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="dpp-scanner-dialog"
        className="sm:max-w-md"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <QrCode className="h-5 w-5 text-[hsl(var(--accent))]" />
            {t('dpp.scanner.title')}
          </DialogTitle>
          <DialogDescription>{t('dpp.scanner.subtitle')}</DialogDescription>
        </DialogHeader>

        <Tabs value={mode} onValueChange={setMode} className="mt-2">
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="camera" data-testid="dpp-scanner-tab-camera">
              <Camera className="h-4 w-4 me-2" /> {t('dpp.scanner.tabCamera')}
            </TabsTrigger>
            <TabsTrigger value="file" data-testid="dpp-scanner-tab-file">
              <FileImage className="h-4 w-4 me-2" /> {t('dpp.scanner.tabFile')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="camera" className="mt-4">
            <div
              className={cn(
                'relative rounded-xl overflow-hidden bg-muted aspect-square w-full',
                'ring-1 ring-border',
              )}
            >
              <div id={readerId} data-testid="dpp-camera-reader" className="w-full h-full" />
              {!cameraReady && !cameraError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground">
                  <Loader2 className="h-6 w-6 animate-spin" />
                  <span className="text-sm">{t('dpp.scanner.starting')}</span>
                </div>
              )}
              {cameraError && (
                <div
                  data-testid="dpp-camera-error"
                  className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center p-6"
                >
                  <X className="h-8 w-8 text-destructive" />
                  <p className="text-sm text-muted-foreground">{cameraError}</p>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setMode('file')}
                    data-testid="dpp-camera-fallback-to-file"
                  >
                    <FileImage className="h-4 w-4 me-2" />
                    {t('dpp.scanner.switchToFile')}
                  </Button>
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              {t('dpp.scanner.cameraHint')}
            </p>
          </TabsContent>

          <TabsContent value="file" className="mt-4">
            <label
              htmlFor="dpp-file-input"
              data-testid="dpp-file-drop"
              className={cn(
                'flex flex-col items-center justify-center rounded-xl border-2 border-dashed',
                'border-border bg-muted/30 hover:bg-muted/60 transition-colors',
                'cursor-pointer aspect-square w-full',
              )}
            >
              {fileBusy ? (
                <>
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mb-2" />
                  <span className="text-sm text-muted-foreground">
                    {t('dpp.scanner.decoding')}
                  </span>
                </>
              ) : (
                <>
                  <FileImage className="h-10 w-10 text-muted-foreground mb-3" />
                  <span className="text-sm font-medium">
                    {t('dpp.scanner.chooseFile')}
                  </span>
                  <span className="text-xs text-muted-foreground mt-1">
                    {t('dpp.scanner.fileHint')}
                  </span>
                </>
              )}
              <input
                id="dpp-file-input"
                type="file"
                accept="image/*"
                className="hidden"
                data-testid="dpp-file-input"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = '';
                  if (f) handleFile(f);
                }}
              />
            </label>
          </TabsContent>
        </Tabs>

        <DialogFooter className="mt-2">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            data-testid="dpp-scanner-cancel"
          >
            {t('common.cancel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DppScanner;
