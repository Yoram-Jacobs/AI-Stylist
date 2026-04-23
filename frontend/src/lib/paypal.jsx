/**
 * PayPalProvider + PayPalCheckoutButton (Phase 4P)
 *
 * Fetches /paypal/config once per session and wraps the (sub)tree in
 * `<PayPalScriptProvider>`. The SDK is loaded lazily with the resolved
 * client_id + default currency. When PayPal is in `mock_mode` (backend
 * fallback when credentials fail) we render a plain "Confirm payment"
 * button and skip the PayPal JS SDK entirely — this keeps dev/demo
 * flows working without real keys.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { PayPalScriptProvider, PayPalButtons } from '@paypal/react-paypal-js';
import { Button } from '@/components/ui/button';
import { Loader2, CreditCard } from 'lucide-react';
import { api } from '@/lib/api';

const PayPalCtx = createContext(null);

export function PayPalProvider({ children }) {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const c = await api.paypalConfig();
        if (!cancelled) setConfig(c);
      } catch {
        if (!cancelled) {
          setConfig({
            configured: false,
            mock_mode: true,
            env: 'mock',
            client_id: '',
            default_currency: 'USD',
            supported_currencies: ['USD'],
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ config }), [config]);

  // When config is still loading or mock_mode is active, skip the SDK
  // loader entirely — PayPalCheckoutButton will fall back to a plain
  // Button in mock mode, so there's no need to load anything from
  // PayPal's CDN.
  const shouldLoadSdk =
    !!config && config.configured && !config.mock_mode && !!config.client_id;

  const inner = <PayPalCtx.Provider value={value}>{children}</PayPalCtx.Provider>;

  if (!shouldLoadSdk) return inner;

  return (
    <PayPalScriptProvider
      options={{
        clientId: config.client_id,
        currency: config.default_currency || 'USD',
        intent: 'capture',
        components: 'buttons',
      }}
    >
      {inner}
    </PayPalScriptProvider>
  );
}

export function usePayPal() {
  const ctx = useContext(PayPalCtx);
  return ctx?.config || null;
}

/**
 * PayPalCheckoutButton
 *
 * Props:
 *  - createOrder: async () => { order_id, ...ctx } — caller-provided function
 *      that hits backend to create an order and returns any metadata
 *      needed during capture.
 *  - captureOrder: async ({ order_id, ctx }) => result — caller-provided
 *      function that hits backend to capture the order.
 *  - onSuccess: (result) => void
 *  - onError?: (err) => void
 *  - amountLabel?: string — fallback label for the mock button.
 *  - disabled?: boolean
 */
export function PayPalCheckoutButton({
  createOrder,
  captureOrder,
  onSuccess,
  onError,
  amountLabel = 'Pay with PayPal',
  disabled = false,
  className = '',
  testId = 'paypal-checkout-button',
}) {
  const config = usePayPal();
  const [busy, setBusy] = useState(false);
  const [ctx, setCtx] = useState(null);

  const handleCreate = useCallback(async () => {
    const res = await createOrder();
    setCtx(res);
    return res?.order_id;
  }, [createOrder]);

  const handleApprove = useCallback(
    async (data) => {
      try {
        const out = await captureOrder({ order_id: data.orderID, ctx });
        onSuccess?.(out);
      } catch (err) {
        onError?.(err);
      }
    },
    [captureOrder, ctx, onSuccess, onError],
  );

  // MOCK MODE: no real PayPal SDK — just run create/capture sequentially.
  const isMock = !config || !config.configured || config.mock_mode;
  if (isMock) {
    const onClick = async () => {
      if (disabled || busy) return;
      setBusy(true);
      try {
        const res = await createOrder();
        const out = await captureOrder({
          order_id: res?.order_id,
          ctx: res,
        });
        onSuccess?.(out);
      } catch (err) {
        onError?.(err);
      } finally {
        setBusy(false);
      }
    };
    return (
      <Button
        type="button"
        onClick={onClick}
        disabled={disabled || busy}
        className={`rounded-xl ${className}`}
        data-testid={`${testId}-mock`}
      >
        {busy ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <>
            <CreditCard className="h-4 w-4 me-2" />
            {amountLabel}
            <span className="ms-2 text-[10px] opacity-70 uppercase tracking-wide">
              (mock)
            </span>
          </>
        )}
      </Button>
    );
  }

  // Real PayPal Smart Buttons
  return (
    <div className={className} data-testid={testId}>
      <PayPalButtons
        style={{
          layout: 'horizontal',
          color: 'gold',
          shape: 'pill',
          label: 'paypal',
          tagline: false,
          height: 40,
        }}
        disabled={disabled}
        createOrder={handleCreate}
        onApprove={handleApprove}
        onError={(err) => onError?.(err)}
      />
    </div>
  );
}
