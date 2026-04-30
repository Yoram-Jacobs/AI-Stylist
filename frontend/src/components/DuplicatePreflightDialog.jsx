import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Star, X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

/**
 * Phase Z2 — pre-flight duplicate confirmation dialog.
 *
 * Shown to the user BEFORE any analyze / Gemini / SegFormer cost is
 * incurred, so duplicates are caught for free. Designed for the
 * interactive (≤5 photos) path: a scrollable list of every photo the
 * backend's /closet/preflight reported as a SHA-256 collision, each row
 * showing the existing closet item beside the new upload's filename
 * and a per-row Skip / "Add anyway ⭐" pair.
 *
 * The component is purely presentational — all state machinery lives
 * in `AddItem.jsx`, which feeds in:
 *
 *   matches:   array of { sha256, filename, size_bytes, existing,
 *                          previewUrl }      (previewUrl is the
 *                          in-browser data URL of the new upload so
 *                          the side-by-side compare needs zero round
 *                          trips)
 *   open:      boolean
 *   onResolve: (decisions) => void
 *      decisions is `Record<sha256, "skip" | "add">`
 *      called once when the user finishes the dialog (per-row choices
 *      OR one of the bulk action buttons).
 *
 * Defaults: every match starts as "skip" (safer — the user has to
 * actively press the red ⭐ to add a known duplicate).
 */
export default function DuplicatePreflightDialog({
  matches,
  open,
  onResolve,
}) {
  const { t } = useTranslation();
  const [decisions, setDecisions] = useState({});

  useEffect(() => {
    if (!open) return;
    // Reset on each open so a stale set of decisions can't leak into
    // a brand-new upload session.
    const init = {};
    (matches || []).forEach((m) => {
      init[m.matchKey] = "skip";
    });
    setDecisions(init);
  }, [open, matches]);

  const handleRow = (key, choice) =>
    setDecisions((prev) => ({ ...prev, [key]: choice }));

  const skipAll = () => {
    const all = {};
    (matches || []).forEach((m) => (all[m.matchKey] = "skip"));
    onResolve(all);
  };

  const addAll = () => {
    const all = {};
    (matches || []).forEach((m) => (all[m.matchKey] = "add"));
    onResolve(all);
  };

  const finish = () => {
    onResolve(decisions);
  };

  const total = (matches || []).length;
  const willAdd = Object.values(decisions).filter((v) => v === "add").length;

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        // Pressing Esc / clicking outside = Cancel = "skip everything".
        if (!o) skipAll();
      }}
    >
      <DialogContent
        className="max-w-2xl"
        data-testid="duplicate-preflight-dialog"
      >
        <DialogHeader>
          <DialogTitle data-testid="duplicate-preflight-title">
            {t("addItem.preflight.title", {
              count: total,
              defaultValue: `${total} of your selected photos look like duplicates`,
            })}
          </DialogTitle>
          <DialogDescription>
            {t("addItem.preflight.body", {
              defaultValue:
                "These exact files already exist in your closet. Skip them — or click the red ⭐ to add anyway. The Stylist Brain will leave starred duplicates out of outfit suggestions so it can't recommend the same garment twice.",
            })}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[55vh] pr-3">
          <div
            className="flex flex-col gap-3"
            data-testid="duplicate-preflight-list"
          >
            {(matches || []).map((m) => {
              const decision = decisions[m.matchKey] || "skip";
              const shortKey = (m.matchKey || "").slice(0, 8);
              return (
                <div
                  key={m.matchKey}
                  className="flex items-stretch gap-3 rounded-lg border bg-muted/30 p-3"
                  data-testid={`duplicate-preflight-row-${shortKey}`}
                >
                  {/* Existing closet thumbnail */}
                  <div className="flex shrink-0 flex-col items-center gap-1">
                    <div className="h-20 w-20 overflow-hidden rounded-md border bg-background">
                      {m.existing?.thumbnail_data_url ? (
                        <img
                          src={m.existing.thumbnail_data_url}
                          alt={m.existing.title}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-[10px] text-muted-foreground">
                          {t("addItem.preflight.noThumb", {
                            defaultValue: "no preview",
                          })}
                        </div>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      {t("addItem.preflight.existing", {
                        defaultValue: "in closet",
                      })}
                    </span>
                  </div>

                  {/* New upload thumbnail (data URL, free, no fetch) */}
                  <div className="flex shrink-0 flex-col items-center gap-1">
                    <div className="h-20 w-20 overflow-hidden rounded-md border bg-background">
                      {m.previewUrl ? (
                        <img
                          src={m.previewUrl}
                          alt={m.filename || "upload"}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-[10px] text-muted-foreground">
                          {m.filename || "upload"}
                        </div>
                      )}
                    </div>
                    <span className="text-[10px] text-muted-foreground">
                      {t("addItem.preflight.incoming", {
                        defaultValue: "new upload",
                      })}
                    </span>
                  </div>

                  {/* Meta + per-row controls */}
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="truncate text-sm font-medium">
                      {m.existing?.title ||
                        t("addItem.preflight.untitled", {
                          defaultValue: "Existing item",
                        })}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {[m.existing?.item_type, m.existing?.color]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    <div className="mt-1 truncate text-xs text-muted-foreground">
                      {m.filename ||
                        t("addItem.preflight.unnamedFile", {
                          defaultValue: "Untitled file",
                        })}
                      {m.size_bytes
                        ? ` · ${(m.size_bytes / (1024 * 1024)).toFixed(2)} MB`
                        : ""}
                    </div>

                    <div className="mt-auto flex items-center justify-end gap-2 pt-2">
                      <Button
                        type="button"
                        variant={decision === "skip" ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleRow(m.matchKey, "skip")}
                        data-testid={`duplicate-preflight-skip-${shortKey}`}
                      >
                        <X className="mr-1 h-3.5 w-3.5" />
                        {t("addItem.preflight.rowSkip", {
                          defaultValue: "Skip",
                        })}
                      </Button>
                      <Button
                        type="button"
                        variant={decision === "add" ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleRow(m.matchKey, "add")}
                        className={
                          decision === "add"
                            ? "bg-rose-600 text-white hover:bg-rose-600/90"
                            : ""
                        }
                        data-testid={`duplicate-preflight-add-${shortKey}`}
                      >
                        <Star
                          className={`mr-1 h-3.5 w-3.5 ${
                            decision === "add"
                              ? "fill-white"
                              : "fill-rose-500 text-rose-500"
                          }`}
                        />
                        {t("addItem.preflight.rowAdd", {
                          defaultValue: "Add anyway",
                        })}
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </ScrollArea>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-muted-foreground">
            {t("addItem.preflight.summary", {
              willAdd,
              willSkip: total - willAdd,
              defaultValue: `${willAdd} will be added · ${total - willAdd} will be skipped`,
            })}
          </span>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={skipAll}
              data-testid="duplicate-preflight-skip-all"
            >
              {t("addItem.preflight.skipAll", {
                defaultValue: "Skip all duplicates",
              })}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addAll}
              data-testid="duplicate-preflight-add-all"
              className="border-rose-200 text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-400 dark:hover:bg-rose-950"
            >
              <Star className="mr-1 h-3.5 w-3.5 fill-rose-500 text-rose-500" />
              {t("addItem.preflight.addAll", {
                defaultValue: "Add all anyway",
              })}
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={finish}
              data-testid="duplicate-preflight-confirm"
            >
              {t("addItem.preflight.confirm", {
                defaultValue: "Continue",
              })}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
