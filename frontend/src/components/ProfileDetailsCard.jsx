import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, Image as ImgIcon, Save, Trash2, Loader2, Sparkles } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

/**
 * Downscale a selected image in-browser before we ship it to Mongo. We cap
 * the long edge to `maxEdge` px and re-encode as JPEG @ q=0.82 — this keeps
 * the stored data URL comfortably under Mongo's 16MB doc ceiling while
 * remaining high enough fidelity for the stylist to read.
 */
async function fileToDataUrl(file, maxEdge = 1280) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxEdge / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL('image/jpeg', 0.82));
      };
      img.onerror = reject;
      img.src = reader.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const STATUS_OPTIONS = ['single', 'married', 'divorced', 'widowed'];
const SEX_OPTIONS = ['female', 'male'];
const HAIR_LENGTH = ['short', 'medium', 'long'];
const HAIR_TYPE = ['straight', 'wavy', 'curly', 'coily'];

function PhotoSlot({ label, value, onChange, testid }) {
  const { t } = useTranslation();
  const inputRef = useRef(null);
  const cameraRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const pick = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const url = await fileToDataUrl(file, 1024);
      onChange(url);
    } catch {
      toast.error(t('common.error'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="rounded-2xl border border-border p-3 bg-secondary/40"
      data-testid={`profile-photo-${testid}`}
    >
      <div className="caps-label text-muted-foreground mb-2">{label}</div>
      <div className="flex items-center gap-3">
        <div className="relative h-20 w-20 rounded-xl overflow-hidden bg-background border border-border shrink-0">
          {value ? (
            <img
              src={value}
              alt={label}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="h-full w-full flex items-center justify-center text-muted-foreground">
              <ImgIcon className="h-5 w-5 opacity-60" />
            </div>
          )}
        </div>
        <div className="flex-1 flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="rounded-lg"
            disabled={busy}
            onClick={() => cameraRef.current?.click()}
            data-testid={`profile-photo-${testid}-camera-btn`}
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <>
                <Camera className="h-3.5 w-3.5 me-1" /> {t('profile.takePhoto')}
              </>
            )}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="rounded-lg"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            data-testid={`profile-photo-${testid}-upload-btn`}
          >
            <ImgIcon className="h-3.5 w-3.5 me-1" />
            {value ? t('profile.replacePhoto') : t('profile.uploadPhoto')}
          </Button>
          {value && (
            <Button
              size="sm"
              variant="ghost"
              className="rounded-lg text-rose-700"
              disabled={busy}
              onClick={() => onChange(null)}
              data-testid={`profile-photo-${testid}-remove-btn`}
            >
              <Trash2 className="h-3.5 w-3.5 me-1" />
              {t('profile.removePhoto')}
            </Button>
          )}
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        // `capture` is honoured on mobile — opens the camera directly.
        capture="user"
        className="hidden"
        onChange={(e) => pick(e.target.files?.[0])}
      />
    </div>
  );
}

function Field({ label, children, htmlFor }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={htmlFor} className="caps-label text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

export function ProfileDetailsCard() {
  const { t } = useTranslation();
  const { user, updateUserLocal } = useAuth();

  const initial = useMemo(
    () => ({
      first_name: user?.first_name || '',
      last_name: user?.last_name || '',
      phone: user?.phone || '',
      date_of_birth: user?.date_of_birth || '',
      sex: user?.sex || '',
      personal_status: user?.personal_status || '',
      address: {
        line1: user?.address?.line1 || '',
        line2: user?.address?.line2 || '',
        city: user?.address?.city || '',
        region: user?.address?.region || '',
        postal_code: user?.address?.postal_code || '',
        country: user?.address?.country || '',
      },
      units: {
        weight: user?.units?.weight || 'kg',
        length: user?.units?.length || 'cm',
      },
      face_photo_url: user?.face_photo_url || '',
      body_photo_url: user?.body_photo_url || '',
      body_measurements: {
        height: user?.body_measurements?.height || '',
        weight: user?.body_measurements?.weight || '',
        shirt_size: user?.body_measurements?.shirt_size || '',
        shoulders: user?.body_measurements?.shoulders || '',
        arm_length: user?.body_measurements?.arm_length || '',
        chest: user?.body_measurements?.chest || '',
        waist: user?.body_measurements?.waist || '',
        hip: user?.body_measurements?.hip || '',
        sleeve: user?.body_measurements?.sleeve || '',
        pants_size: user?.body_measurements?.pants_size || '',
        inseam: user?.body_measurements?.inseam || '',
        outseam: user?.body_measurements?.outseam || '',
        shoe_size: user?.body_measurements?.shoe_size || '',
        foot_length: user?.body_measurements?.foot_length || '',
        bra_size: user?.body_measurements?.bra_size || '',
        dress_size: user?.body_measurements?.dress_size || '',
      },
      hair: {
        length: user?.hair?.length || '',
        type: user?.hair?.type || '',
        color: user?.hair?.color || '',
        style: user?.hair?.style || '',
      },
      professional: {
        is_professional: !!user?.professional?.is_professional,
        profession: user?.professional?.profession || '',
        approval_status: user?.professional?.approval_status || 'self',
        business: {
          name: user?.professional?.business?.name || '',
          address: user?.professional?.business?.address || '',
          phone: user?.professional?.business?.phone || '',
          email: user?.professional?.business?.email || '',
          website: user?.professional?.business?.website || '',
          description: user?.professional?.business?.description || '',
        },
      },
    }),
    [user],
  );

  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setNested = (parent, k, v) =>
    setForm((f) => ({ ...f, [parent]: { ...f[parent], [k]: v } }));

  const isFemale = form.sex === 'female';
  const wUnit = form.units.weight === 'lb' ? 'lb' : 'kg';
  const lUnit = form.units.length === 'in' ? 'in' : 'cm';
  const autofilledFromGoogle =
    !!user?.google_connected &&
    (!!user?.first_name || !!user?.last_name || !!user?.avatar_url);

  const save = async () => {
    setBusy(true);
    try {
      // Strip empty-string values so we don't clobber defaults server-side.
      const prune = (obj) =>
        Object.fromEntries(
          Object.entries(obj).filter(
            ([, v]) => v !== '' && v !== null && v !== undefined,
          ),
        );
      const payload = {
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        phone: form.phone || null,
        date_of_birth: form.date_of_birth || null,
        sex: form.sex || null,
        personal_status: form.personal_status || null,
        address: prune(form.address),
        units: { weight: wUnit, length: lUnit },
        face_photo_url: form.face_photo_url || null,
        body_photo_url: form.body_photo_url || null,
        body_measurements: prune(form.body_measurements),
        hair: prune(form.hair),
        professional: form.professional.is_professional
          ? {
              is_professional: true,
              profession: form.professional.profession || null,
              approval_status: form.professional.approval_status || 'self',
              business: prune(form.professional.business),
            }
          : { is_professional: false },
      };
      const updated = await api.patchMe(payload);
      updateUserLocal?.(updated);
      toast.success(t('profile.savedProfile'));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t('profile.saveFailed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      className="rounded-[calc(var(--radius)+6px)] shadow-editorial"
      data-testid="profile-details-card"
    >
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <div className="caps-label text-muted-foreground">
              {t('profile.sections.identity')}
            </div>
            <h3 className="font-display text-xl mt-0.5">{t('profile.title')}</h3>
          </div>
          {autofilledFromGoogle && (
            <Badge
              variant="outline"
              className="text-[11px] bg-card rounded-full"
              data-testid="profile-google-autofill-badge"
            >
              <Sparkles className="h-3 w-3 me-1 text-[hsl(var(--accent))]" />
              {t('profile.autofilledFromGoogle')}
            </Badge>
          )}
        </div>

        <Accordion
          type="multiple"
          defaultValue={['identity']}
          className="w-full"
        >
          {/* --- Identity --- */}
          <AccordionItem value="identity">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-identity"
            >
              {t('profile.sections.identity')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label={t('profile.firstName')} htmlFor="f-first">
                  <Input
                    id="f-first"
                    value={form.first_name}
                    onChange={(e) => setField('first_name', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-field-first_name"
                  />
                </Field>
                <Field label={t('profile.lastName')} htmlFor="f-last">
                  <Input
                    id="f-last"
                    value={form.last_name}
                    onChange={(e) => setField('last_name', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-field-last_name"
                  />
                </Field>
                <Field label={t('profile.email')}>
                  <Input
                    value={user?.email || ''}
                    readOnly
                    className="rounded-xl bg-secondary/60"
                    data-testid="profile-field-email"
                  />
                </Field>
                <Field label={t('profile.dob')} htmlFor="f-dob">
                  <Input
                    id="f-dob"
                    type="date"
                    value={form.date_of_birth || ''}
                    onChange={(e) => setField('date_of_birth', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-field-date_of_birth"
                  />
                </Field>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Contact --- */}
          <AccordionItem value="contact">
            <AccordionTrigger className="caps-label" data-testid="profile-accordion-contact">
              {t('profile.sections.contact')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label={t('profile.phone')} htmlFor="f-phone">
                  <Input
                    id="f-phone"
                    type="tel"
                    value={form.phone}
                    onChange={(e) => setField('phone', e.target.value)}
                    placeholder={t('profile.phonePlaceholder')}
                    className="rounded-xl"
                    data-testid="profile-field-phone"
                  />
                </Field>
                <Field label={t('profile.addressLine1')} htmlFor="f-l1">
                  <Input
                    id="f-l1"
                    value={form.address.line1}
                    onChange={(e) => setNested('address', 'line1', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-field-address_line1"
                  />
                </Field>
                <Field label={t('profile.addressLine2')} htmlFor="f-l2">
                  <Input
                    id="f-l2"
                    value={form.address.line2}
                    onChange={(e) => setNested('address', 'line2', e.target.value)}
                    className="rounded-xl"
                  />
                </Field>
                <Field label={t('profile.city')} htmlFor="f-city">
                  <Input
                    id="f-city"
                    value={form.address.city}
                    onChange={(e) => setNested('address', 'city', e.target.value)}
                    className="rounded-xl"
                  />
                </Field>
                <Field label={t('profile.region')} htmlFor="f-region">
                  <Input
                    id="f-region"
                    value={form.address.region}
                    onChange={(e) => setNested('address', 'region', e.target.value)}
                    className="rounded-xl"
                  />
                </Field>
                <Field label={t('profile.postalCode')} htmlFor="f-zip">
                  <Input
                    id="f-zip"
                    value={form.address.postal_code}
                    onChange={(e) => setNested('address', 'postal_code', e.target.value)}
                    className="rounded-xl"
                  />
                </Field>
                <Field label={t('profile.country')} htmlFor="f-country">
                  <Input
                    id="f-country"
                    value={form.address.country}
                    onChange={(e) => setNested('address', 'country', e.target.value)}
                    className="rounded-xl"
                  />
                </Field>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Demographics --- */}
          <AccordionItem value="demographics">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-demographics"
            >
              {t('profile.sections.demographics')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Field label={t('profile.sex')}>
                  <Select
                    value={form.sex || ''}
                    onValueChange={(v) => setField('sex', v || '')}
                  >
                    <SelectTrigger
                      className="rounded-xl"
                      data-testid="profile-field-sex"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SEX_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>
                          {t(`profile.sex_${s}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t('profile.personalStatus')}>
                  <Select
                    value={form.personal_status || ''}
                    onValueChange={(v) => setField('personal_status', v || '')}
                  >
                    <SelectTrigger
                      className="rounded-xl"
                      data-testid="profile-field-personal_status"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUS_OPTIONS.map((s) => (
                        <SelectItem key={s} value={s}>
                          {t(`profile.status_${s}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Preferences (units) --- */}
          <AccordionItem value="preferences">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-preferences"
            >
              {t('profile.sections.preferences')} — {t('profile.units')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t('profile.unitsWeight')}>
                  <Select
                    value={wUnit}
                    onValueChange={(v) => setNested('units', 'weight', v)}
                  >
                    <SelectTrigger className="rounded-xl" data-testid="profile-unit-weight">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="kg">{t('profile.unitKg')}</SelectItem>
                      <SelectItem value="lb">{t('profile.unitLb')}</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t('profile.unitsLength')}>
                  <Select
                    value={lUnit}
                    onValueChange={(v) => setNested('units', 'length', v)}
                  >
                    <SelectTrigger className="rounded-xl" data-testid="profile-unit-length">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cm">{t('profile.unitCm')}</SelectItem>
                      <SelectItem value="in">{t('profile.unitIn')}</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Photos --- */}
          <AccordionItem value="photos">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-photos"
            >
              {t('profile.sections.photos')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <PhotoSlot
                  label={t('profile.facePhoto')}
                  value={form.face_photo_url}
                  onChange={(v) => setField('face_photo_url', v)}
                  testid="face"
                />
                <PhotoSlot
                  label={t('profile.bodyPhoto')}
                  value={form.body_photo_url}
                  onChange={(v) => setField('body_photo_url', v)}
                  testid="body"
                />
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Measurements --- */}
          <AccordionItem value="measurements">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-measurements"
            >
              {t('profile.sections.measurements')}
            </AccordionTrigger>
            <AccordionContent>
              <MeasurementsGrid
                form={form}
                onChange={(k, v) => setNested('body_measurements', k, v)}
                wUnit={wUnit}
                lUnit={lUnit}
                isFemale={isFemale}
              />
            </AccordionContent>
          </AccordionItem>

          {/* --- Hair --- */}
          <AccordionItem value="hair">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-hair"
            >
              {t('profile.sections.hair')}
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-2 gap-3">
                <Field label={t('profile.hairFields.length')}>
                  <Select
                    value={form.hair.length || ''}
                    onValueChange={(v) => setNested('hair', 'length', v)}
                  >
                    <SelectTrigger className="rounded-xl" data-testid="profile-hair-length">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HAIR_LENGTH.map((k) => (
                        <SelectItem key={k} value={k}>
                          {t(`profile.hairFields.length_${k}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t('profile.hairFields.type')}>
                  <Select
                    value={form.hair.type || ''}
                    onValueChange={(v) => setNested('hair', 'type', v)}
                  >
                    <SelectTrigger className="rounded-xl" data-testid="profile-hair-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HAIR_TYPE.map((k) => (
                        <SelectItem key={k} value={k}>
                          {t(`profile.hairFields.type_${k}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t('profile.hairFields.color')}>
                  <Input
                    value={form.hair.color}
                    onChange={(e) => setNested('hair', 'color', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-hair-color"
                  />
                </Field>
                <Field label={t('profile.hairFields.style')}>
                  <Input
                    value={form.hair.style}
                    onChange={(e) => setNested('hair', 'style', e.target.value)}
                    className="rounded-xl"
                    data-testid="profile-hair-style"
                  />
                </Field>
              </div>
            </AccordionContent>
          </AccordionItem>

          {/* --- Professional (Phase U) --- */}
          <AccordionItem value="professional">
            <AccordionTrigger
              className="caps-label"
              data-testid="profile-accordion-professional"
            >
              {t('profile.professional.sectionTitle')}
              {form.professional.is_professional && (
                <Badge
                  variant="outline"
                  className="ms-2 text-[10px] bg-card rounded-full"
                >
                  {t('ads.status_active')}
                </Badge>
              )}
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-4">
                <div className="flex items-start gap-3 rounded-xl border border-border p-3 bg-secondary/40">
                  <Switch
                    checked={form.professional.is_professional}
                    onCheckedChange={(v) =>
                      setField('professional', {
                        ...form.professional,
                        is_professional: !!v,
                      })
                    }
                    data-testid="profile-professional-toggle"
                  />
                  <div className="flex-1">
                    <div className="font-medium text-sm">
                      {t('profile.professional.checkboxLabel')}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {t('profile.professional.checkboxHint')}
                    </div>
                  </div>
                  {form.professional.approval_status === 'hidden' && (
                    <Badge
                      variant="outline"
                      className="bg-card text-[10px] rounded-full border-rose-400/40 text-rose-700"
                    >
                      {t('profile.professional.hiddenBadge')}
                    </Badge>
                  )}
                </div>

                {form.professional.is_professional && (
                  <>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <Field label={t('profile.professional.profession')}>
                        <Input
                          value={form.professional.profession}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              profession: e.target.value,
                            })
                          }
                          placeholder={t(
                            'profile.professional.professionPlaceholder',
                          )}
                          className="rounded-xl"
                          data-testid="profile-professional-profession"
                        />
                      </Field>
                      <Field label={t('profile.professional.businessName')}>
                        <Input
                          value={form.professional.business.name}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              business: {
                                ...form.professional.business,
                                name: e.target.value,
                              },
                            })
                          }
                          className="rounded-xl"
                          data-testid="profile-professional-business-name"
                        />
                      </Field>
                      <Field label={t('profile.professional.businessAddress')}>
                        <Input
                          value={form.professional.business.address}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              business: {
                                ...form.professional.business,
                                address: e.target.value,
                              },
                            })
                          }
                          className="rounded-xl"
                          data-testid="profile-professional-business-address"
                        />
                      </Field>
                      <Field label={t('profile.professional.businessPhone')}>
                        <Input
                          type="tel"
                          value={form.professional.business.phone}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              business: {
                                ...form.professional.business,
                                phone: e.target.value,
                              },
                            })
                          }
                          className="rounded-xl"
                          data-testid="profile-professional-business-phone"
                        />
                      </Field>
                      <Field label={t('profile.professional.businessEmail')}>
                        <Input
                          type="email"
                          value={form.professional.business.email}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              business: {
                                ...form.professional.business,
                                email: e.target.value,
                              },
                            })
                          }
                          className="rounded-xl"
                          data-testid="profile-professional-business-email"
                        />
                      </Field>
                      <Field label={t('profile.professional.businessWebsite')}>
                        <Input
                          type="url"
                          placeholder="https://"
                          value={form.professional.business.website}
                          onChange={(e) =>
                            setField('professional', {
                              ...form.professional,
                              business: {
                                ...form.professional.business,
                                website: e.target.value,
                              },
                            })
                          }
                          className="rounded-xl"
                          data-testid="profile-professional-business-website"
                        />
                      </Field>
                    </div>
                    <Field label={t('profile.professional.businessDescription')}>
                      <Textarea
                        rows={3}
                        value={form.professional.business.description}
                        onChange={(e) =>
                          setField('professional', {
                            ...form.professional,
                            business: {
                              ...form.professional.business,
                              description: e.target.value,
                            },
                          })
                        }
                        className="rounded-xl"
                        data-testid="profile-professional-business-description"
                      />
                    </Field>
                    <div className="text-xs text-muted-foreground">
                      <Sparkles className="inline h-3 w-3 me-1 text-[hsl(var(--accent))]" />
                      {t('profile.professional.visibilityNote')}
                    </div>
                  </>
                )}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        <div className="flex justify-end">
          <Button
            onClick={save}
            disabled={busy}
            className="rounded-xl"
            data-testid="profile-details-save-btn"
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <>
                <Save className="h-4 w-4 me-2" /> {t('profile.saveProfile')}
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Dedicated grid: swaps labelled units, adds female-only rows conditionally.
 */
function MeasurementsGrid({ form, onChange, wUnit, lUnit, isFemale }) {
  const { t } = useTranslation();
  const len = (raw) => (raw ? `${raw} ${lUnit}` : '');

  const Num = ({ field, label, unit = 'len' }) => (
    <Field label={`${label} (${unit === 'wt' ? wUnit : lUnit})`}>
      <Input
        type="text"
        inputMode="decimal"
        value={form.body_measurements[field] ?? ''}
        onChange={(e) => onChange(field, e.target.value)}
        className="rounded-xl"
        data-testid={`profile-measurement-${field}`}
      />
    </Field>
  );
  const Txt = ({ field, label }) => (
    <Field label={label}>
      <Input
        value={form.body_measurements[field] ?? ''}
        onChange={(e) => onChange(field, e.target.value)}
        className="rounded-xl"
        data-testid={`profile-measurement-${field}`}
      />
    </Field>
  );
  // eslint-disable-next-line no-unused-vars
  const _ = len; // keep helper around for future per-unit display formatting
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <Num field="height" label={t('profile.measurements.height')} />
      <Num field="weight" label={t('profile.measurements.weight')} unit="wt" />
      <Txt field="shirt_size" label={t('profile.measurements.shirtSize')} />
      <Num field="shoulders" label={t('profile.measurements.shoulders')} />
      <Num field="arm_length" label={t('profile.measurements.armLength')} />
      <Num field="chest" label={t('profile.measurements.chest')} />
      <Num field="waist" label={t('profile.measurements.waist')} />
      <Num field="hip" label={t('profile.measurements.hip')} />
      <Num field="sleeve" label={t('profile.measurements.sleeve')} />
      <Txt field="pants_size" label={t('profile.measurements.pantsSize')} />
      <Num field="inseam" label={t('profile.measurements.inseam')} />
      <Num field="outseam" label={t('profile.measurements.outseam')} />
      <Txt field="shoe_size" label={t('profile.measurements.shoeSize')} />
      <Num field="foot_length" label={t('profile.measurements.footLength')} />
      {isFemale && (
        <>
          <Txt field="bra_size" label={t('profile.measurements.braSize')} />
          <Txt field="dress_size" label={t('profile.measurements.dressSize')} />
        </>
      )}
    </div>
  );
}
