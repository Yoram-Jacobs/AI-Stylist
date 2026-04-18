{
  "brand": {
    "name": "DressApp",
    "design_personality": [
      "editorial boutique magazine",
      "quiet-luxury minimal",
      "camera-first utility hidden behind polish",
      "sustainability-forward (swap/donate cues)",
      "AI stylist feels like a fashion editor, not a chatbot"
    ],
    "north_star": "Make every screen feel like a curated spread: strong typography, generous whitespace, tactile cards, and fast, confident interactions—especially on mobile."
  },

  "design_tokens": {
    "notes": [
      "Implement via CSS custom properties in /app/frontend/src/index.css under :root and .dark (shadcn token style).",
      "Avoid purple for AI surfaces; use ocean-teal + persimmon + ink neutrals.",
      "No transparent backgrounds behind text blocks; use solid card surfaces.",
      "Gradients are decorative only and must stay under 20% viewport coverage."
    ],

    "color_system": {
      "mode": "light + dark",
      "semantic_tokens_hsl": {
        "light": {
          "--background": "36 33% 97%",
          "--foreground": "222 22% 12%",

          "--card": "0 0% 100%",
          "--card-foreground": "222 22% 12%",

          "--popover": "0 0% 100%",
          "--popover-foreground": "222 22% 12%",

          "--primary": "222 22% 12%",
          "--primary-foreground": "36 33% 97%",

          "--secondary": "36 20% 93%",
          "--secondary-foreground": "222 22% 12%",

          "--muted": "36 18% 92%",
          "--muted-foreground": "222 10% 42%",

          "--accent": "174 44% 33%",
          "--accent-foreground": "0 0% 100%",

          "--destructive": "0 72% 52%",
          "--destructive-foreground": "0 0% 100%",

          "--border": "30 14% 86%",
          "--input": "30 14% 86%",
          "--ring": "174 44% 33%",

          "--radius": "0.9rem",

          "--chart-1": "174 44% 33%",
          "--chart-2": "18 78% 56%",
          "--chart-3": "222 22% 12%",
          "--chart-4": "36 18% 92%",
          "--chart-5": "30 14% 86%"
        },
        "dark": {
          "--background": "222 22% 8%",
          "--foreground": "36 33% 97%",

          "--card": "222 22% 10%",
          "--card-foreground": "36 33% 97%",

          "--popover": "222 22% 10%",
          "--popover-foreground": "36 33% 97%",

          "--primary": "36 33% 97%",
          "--primary-foreground": "222 22% 10%",

          "--secondary": "222 16% 14%",
          "--secondary-foreground": "36 33% 97%",

          "--muted": "222 16% 14%",
          "--muted-foreground": "36 10% 72%",

          "--accent": "174 46% 38%",
          "--accent-foreground": "222 22% 8%",

          "--destructive": "0 62% 42%",
          "--destructive-foreground": "0 0% 100%",

          "--border": "222 14% 18%",
          "--input": "222 14% 18%",
          "--ring": "174 46% 38%"
        }
      },

      "brand_extras_hex": {
        "ink": "#14161B",
        "paper": "#FBF8F2",
        "ocean_teal": "#1F6F6B",
        "sea_glass": "#BFD8D2",
        "persimmon": "#E8603C",
        "sand": "#E9E1D6",
        "graphite": "#2A2E36"
      },

      "allowed_gradients": {
        "usage": [
          "Hero/top-of-screen background wash only (max 20% viewport)",
          "Decorative separators behind section titles",
          "Never on cards containing long text"
        ],
        "css_examples": {
          "hero_wash_light": "radial-gradient(900px circle at 20% 10%, rgba(31,111,107,0.14), transparent 55%), radial-gradient(700px circle at 85% 0%, rgba(232,96,60,0.10), transparent 50%)",
          "hero_wash_dark": "radial-gradient(900px circle at 20% 10%, rgba(31,111,107,0.22), transparent 55%), radial-gradient(700px circle at 85% 0%, rgba(232,96,60,0.14), transparent 50%)"
        }
      }
    },

    "typography": {
      "font_pairing": {
        "display": {
          "name": "Gloock",
          "google_fonts": "https://fonts.google.com/specimen/Gloock",
          "usage": "H1/H2, editorial section titles, Trend-Scout headlines"
        },
        "body": {
          "name": "Manrope",
          "google_fonts": "https://fonts.google.com/specimen/Manrope",
          "usage": "UI labels, body copy, chat, tables, forms"
        }
      },
      "css_scaffold": {
        "notes": "Add to /app/frontend/src/index.css (or import in index.html) and set body font-family to Manrope; headings use a utility class.",
        "google_import": "@import url('https://fonts.googleapis.com/css2?family=Gloock&family=Manrope:wght@400;500;600;700&display=swap');",
        "font_vars": {
          "--font-display": "Gloock, ui-serif, Georgia, serif",
          "--font-body": "Manrope, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
        },
        "tailwind_usage": {
          "display_class": "font-[var(--font-display)] tracking-[-0.02em]",
          "body_class": "font-[var(--font-body)]"
        }
      },
      "type_scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl leading-[1.02]",
        "h2": "text-base md:text-lg leading-relaxed",
        "section_title": "text-xl sm:text-2xl tracking-[-0.01em]",
        "body": "text-sm sm:text-base leading-relaxed",
        "small": "text-xs sm:text-sm",
        "caps_label": "text-[11px] uppercase tracking-[0.18em]"
      }
    },

    "spacing_and_grid": {
      "spacing": {
        "base_unit": "4px",
        "recommended_steps_px": [4, 8, 12, 16, 20, 24, 32, 40, 56, 72],
        "rule": "Use 2–3x more whitespace than default shadcn examples; prefer 24/32 gaps between sections."
      },
      "layout": {
        "mobile": {
          "container": "px-4",
          "max_width": "max-w-[480px] for dense flows; allow full width for image grids",
          "bottom_tab_safe_area": "pb-[calc(env(safe-area-inset-bottom)+88px)]"
        },
        "desktop": {
          "container": "mx-auto max-w-6xl px-6",
          "grid": "12-col grid for admin + marketplace detail; 2-col split for stylist (history + chat)"
        }
      }
    },

    "radius_and_shadow": {
      "radius": {
        "global": "--radius: 0.9rem",
        "card": "rounded-[calc(var(--radius)+6px)]",
        "button": "rounded-xl",
        "chip": "rounded-full",
        "drawer_sheet": "rounded-t-[28px]"
      },
      "shadow": {
        "philosophy": "Soft editorial elevation; no harsh drop shadows. Use subtle ambient + crisp keyline.",
        "tokens": {
          "--shadow-sm": "0 1px 0 rgba(20,22,27,0.06), 0 8px 24px rgba(20,22,27,0.06)",
          "--shadow-md": "0 1px 0 rgba(20,22,27,0.08), 0 18px 50px rgba(20,22,27,0.10)",
          "--shadow-focus": "0 0 0 4px rgba(31,111,107,0.22)"
        },
        "tailwind_usage": {
          "card": "shadow-[var(--shadow-sm)]",
          "modal": "shadow-[var(--shadow-md)]"
        }
      }
    },

    "texture": {
      "noise_overlay": {
        "goal": "Add subtle print-like grain to avoid flatness.",
        "implementation": {
          "css": ".noise::before{content:'';position:absolute;inset:0;background-image:url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%22120%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22 numOctaves=%222%22 stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect width=%22120%22 height=%22120%22 filter=%22url(%23n)%22 opacity=%220.08%22/%3E%3C/svg%3E');mix-blend-mode:multiply;pointer-events:none;border-radius:inherit;}",
          "usage": "Apply `relative noise` to hero wrappers and large image cards only (not to text-heavy reading areas)."
        }
      }
    }
  },

  "component_system": {
    "component_path": {
      "shadcn_ui": "/app/frontend/src/components/ui/",
      "primary_components_to_use": [
        "button.jsx",
        "badge.jsx",
        "card.jsx",
        "tabs.jsx",
        "drawer.jsx",
        "sheet.jsx",
        "dialog.jsx",
        "select.jsx",
        "dropdown-menu.jsx",
        "command.jsx",
        "input.jsx",
        "textarea.jsx",
        "switch.jsx",
        "slider.jsx",
        "progress.jsx",
        "skeleton.jsx",
        "scroll-area.jsx",
        "carousel.jsx",
        "calendar.jsx",
        "table.jsx",
        "sonner.jsx"
      ]
    },

    "global_patterns": {
      "data_testid": {
        "rule": "Every interactive + key informational element MUST include data-testid in kebab-case describing role.",
        "examples": [
          "data-testid=\"bottom-tab-closet\"",
          "data-testid=\"closet-filter-color-select\"",
          "data-testid=\"stylist-composer-send-button\"",
          "data-testid=\"marketplace-fee-preview\"",
          "data-testid=\"admin-revenue-kpi\""
        ]
      },

      "buttons": {
        "style": "Luxury / Elegant",
        "variants": {
          "primary": {
            "use": "Primary CTA (Ask Stylist, Publish listing, Save item)",
            "classes": "rounded-xl bg-primary text-primary-foreground shadow-[var(--shadow-sm)] hover:bg-primary/92 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]",
            "motion": "hover: translateY(-1px) via framer-motion; active: scale(0.98)"
          },
          "secondary": {
            "use": "Secondary actions (Preview fees, Add variant)",
            "classes": "rounded-xl bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border",
            "motion": "hover: subtle lift; active: scale(0.99)"
          },
          "ghost": {
            "use": "Icon-only actions (mic, attach, more)",
            "classes": "rounded-xl hover:bg-accent/10 text-foreground",
            "motion": "hover: background fade only (no transform unless wrapped in motion.button)"
          }
        }
      },

      "badges_and_tags": {
        "source_tags": {
          "private": {
            "label": "Private",
            "classes": "bg-[hsl(var(--secondary))] text-foreground border border-border"
          },
          "shared": {
            "label": "Shared",
            "classes": "bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border border-[hsl(var(--accent))]/25"
          },
          "retail": {
            "label": "Retail",
            "classes": "bg-[rgba(232,96,60,0.10)] text-[rgb(232,96,60)] border border-[rgba(232,96,60,0.25)]"
          }
        },
        "season_badges": "Use muted chips with caps_label typography; never rely on color alone—include icon or text."
      },

      "cards": {
        "editorial_card": {
          "classes": "rounded-[calc(var(--radius)+6px)] bg-card text-card-foreground border border-border shadow-[var(--shadow-sm)]",
          "image_rule": "Always keep text on solid card area; image can be top with AspectRatio; add gradient overlay only on image area if needed for legibility."
        },
        "bento_grid": {
          "home": "Use 2-col bento on mobile (stacked), 3–4 col on desktop; mix 1x1 and 2x1 cards for magazine rhythm.",
          "closet": "Use dense image grid with sticky filter bar; cards show 1–2 metadata lines only."
        }
      },

      "forms": {
        "inputs": {
          "classes": "rounded-xl bg-card border border-input focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))]",
          "helper_text": "Use small muted text; errors in destructive with concise copy."
        },
        "selects": "Use shadcn Select + Command for searchable lists (brands, categories).",
        "calendar": "Use shadcn Calendar for date picking (listing availability, etc.)."
      },

      "navigation": {
        "mobile_bottom_tabs": {
          "pattern": "Fixed bottom bar with 5 tabs (Home/Closet/Stylist/Market/Me).",
          "classes": "fixed bottom-0 inset-x-0 bg-background/95 backdrop-blur border-t border-border",
          "interaction": "Active tab uses accent underline + icon fill; haptic-like scale on tap via framer-motion.",
          "a11y": "44px min hit targets; labels always visible."
        },
        "desktop_top_nav": {
          "pattern": "Top nav with breadcrumb + quick actions; left rail optional for admin.",
          "component": "navigation-menu.jsx + breadcrumb.jsx"
        }
      }
    },

    "page_blueprints": {
      "home": {
        "layout": "Editorial feed: hero header (small gradient wash) + Trend-Scout cards + CTA to Stylist.",
        "components": ["card", "carousel", "badge", "button", "skeleton"],
        "key_interactions": [
          "Trend-Scout cards expand into Drawer with full summary + sources",
          "Pull-to-refresh on mobile (optional) with subtle spinner",
          "Weather + Calendar chips are tappable Popovers with details"
        ],
        "testids": [
          "home-trend-scout-feed",
          "home-ask-stylist-cta",
          "home-weather-chip",
          "home-calendar-chip"
        ]
      },

      "closet": {
        "layout": "Sticky filter row + masonry-like grid (use CSS columns or responsive grid). Item tap opens Drawer detail.",
        "components": ["badge", "drawer", "tabs", "select", "command", "scroll-area", "skeleton"],
        "key_interactions": [
          "Long-press (mobile) or right-click (desktop) opens ContextMenu for quick actions (Share, List, Donate)",
          "Filter chips animate in/out; show active filter count",
          "FAB expands into mini-sheet with Capture/Upload options"
        ],
        "testids": [
          "closet-grid",
          "closet-filter-bar",
          "closet-add-item-fab",
          "closet-item-card"
        ]
      },

      "camera_add_item": {
        "layout": "Full-screen camera/upload with segmented preview; metadata stepper.",
        "components": ["aspect-ratio", "progress", "tabs", "button", "sheet", "skeleton"],
        "key_interactions": [
          "Live cutout preview: show before/after toggle (Toggle component)",
          "Edge refinement slider (Slider) with instant preview",
          "Save triggers optimistic UI + toast (sonner)"
        ],
        "loading_states": [
          "SAM-2 segmentation: show skeleton silhouette + progress bar with copy: 'Cutting out your piece…'",
          "If >10s: show secondary line 'Still working—high-res edges take a moment.'"
        ],
        "testids": [
          "add-item-upload-button",
          "add-item-segmentation-preview",
          "add-item-save-button"
        ]
      },

      "item_detail_variants": {
        "layout": "Drawer with image, metadata, and variant carousel (original + edits).",
        "components": ["drawer", "carousel", "tabs", "button", "badge"],
        "key_interactions": [
          "Variant generation uses SD image-to-image: show queued state + skeleton tile",
          "Tap variant to compare with original (split view toggle)",
          "'Make sleeves long' opens Sheet with prompt presets"
        ],
        "testids": [
          "item-detail-drawer",
          "item-variant-carousel",
          "item-generate-variant-button"
        ]
      },

      "stylist_chat": {
        "layout": "Full-screen chat; composer anchored above bottom tabs; optional desktop split view.",
        "components": ["scroll-area", "textarea", "button", "popover", "tabs", "card", "sonner"],
        "key_interactions": [
          "Composer includes: attach image, mic record, send; weather + calendar chips inline",
          "AI reply supports audio playback with waveform (custom component) and transcript toggle",
          "Outfit cards inside messages: swipe horizontally to browse looks"
        ],
        "performance": [
          "Gemini latency 15–25s: show streaming placeholder bubbles + skeleton outfit cards",
          "Allow cancel generation button"
        ],
        "testids": [
          "stylist-chat-thread",
          "stylist-composer-textarea",
          "stylist-composer-mic-button",
          "stylist-composer-send-button",
          "stylist-reply-audio-player"
        ]
      },

      "marketplace": {
        "layout": "Discovery grid with price + fee preview; detail page with breakdown; wizard for listing.",
        "components": ["tabs", "card", "badge", "drawer", "dialog", "progress", "table"],
        "fee_preview_pattern": {
          "rule": "Always show: list price, Stripe fee estimate, platform 7% commission, seller net.",
          "ui": "Collapsed row on card; expands in Drawer on tap."
        },
        "testids": [
          "marketplace-grid",
          "marketplace-item-card",
          "marketplace-fee-breakdown",
          "listing-wizard-next-button",
          "listing-publish-button"
        ]
      },

      "profile_settings": {
        "layout": "Magazine-like settings: grouped cards with short descriptions; dangerous actions separated.",
        "components": ["card", "select", "switch", "button", "separator"],
        "integrations": [
          "Google Calendar connect CTA (OAuth) uses Button + inline status badge",
          "Stripe Connect onboarding CTA uses primary button + explainer"
        ],
        "testids": [
          "settings-style-profile",
          "settings-calendar-connect-button",
          "settings-stripe-connect-button"
        ]
      },

      "admin": {
        "layout": "Clean analytics: KPI cards + charts + tables; role-gated.",
        "components": ["card", "table", "tabs"],
        "library": {
          "recommended": "recharts",
          "install": "npm i recharts",
          "usage": "Use AreaChart for revenue trend; BarChart for take-rate by day; keep palette monochrome + accent teal."
        },
        "testids": [
          "admin-revenue-kpi",
          "admin-users-table",
          "admin-revenue-chart"
        ]
      }
    }
  },

  "motion_language": {
    "library": {
      "recommended": "framer-motion",
      "install": "npm i framer-motion",
      "principles": [
        "Motion should feel like turning pages / sliding cards on a desk.",
        "Use short durations; avoid bouncy overshoot.",
        "Respect prefers-reduced-motion."
      ]
    },
    "timings": {
      "fast": "120–160ms",
      "base": "180–240ms",
      "slow": "320–420ms (drawers/sheets only)"
    },
    "easings": {
      "standard": "[0.2, 0.8, 0.2, 1]",
      "exit": "[0.4, 0, 1, 1]"
    },
    "micro_interactions": [
      "Buttons: hover lift -1px (desktop), active scale 0.98",
      "Cards: hover shows subtle border darken + shadow increase (desktop only)",
      "Chips: selected state animates underline in 160ms",
      "Drawer open: slide up + fade; backdrop blur increases",
      "Skeleton shimmer: keep subtle; avoid high-contrast shimmer"
    ]
  },

  "empty_and_error_states": {
    "tone": "Editorial, concise, supportive. No jokes; no emojis.",
    "microcopy_examples": {
      "closet_empty": {
        "title": "Your closet starts here",
        "body": "Add your first piece—DressApp will tag it and keep it ready for styling, sharing, or listing.",
        "cta": "Add an item"
      },
      "marketplace_empty": {
        "title": "Nothing matching yet",
        "body": "Try widening your filters or check back after today’s Trend-Scout update.",
        "cta": "Clear filters"
      },
      "stylist_latency": {
        "title": "Drafting your look",
        "body": "Pulling your closet, weather, and calendar context. This can take a moment.",
        "cta": "Cancel"
      },
      "network_error": {
        "title": "We couldn’t reach DressApp",
        "body": "Check your connection and try again.",
        "cta": "Retry"
      }
    }
  },

  "accessibility": {
    "wcag": "AA minimum",
    "rules": [
      "Minimum 44px touch targets for bottom tabs, FAB, composer buttons.",
      "Visible focus ring using --ring + --shadow-focus.",
      "Never encode meaning by color alone (source tags include text).",
      "Audio player: provide play/pause button labels, progress slider with aria-valuetext, and transcript toggle.",
      "Respect prefers-reduced-motion: disable parallax/lift transforms."
    ]
  },

  "image_urls": {
    "hero_and_editorial": [
      {
        "category": "home-hero-background",
        "description": "Abstract teal paper-like waves for subtle editorial hero wash (use as decorative background only).",
        "url": "https://images.unsplash.com/photo-1660721858662-9ad9f37447f7?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ],
    "closet_and_flatlay": [
      {
        "category": "closet-empty-state",
        "description": "Minimal flat-lay sweater/wallet image for empty state illustration (keep small, not full-bleed).",
        "url": "https://images.unsplash.com/photo-1654773125909-6d73f0c12407?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ],
    "marketplace_editorial": [
      {
        "category": "marketplace-featured-banner",
        "description": "Warm editorial street-style image for featured collection banner (use with solid text card overlay).",
        "url": "https://images.unsplash.com/photo-1646105659698-1389145bf6a0?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ]
  },

  "instructions_to_main_agent": {
    "priority_changes": [
      "Replace CRA default App.css usage; do not center the app container. Remove/ignore .App-header styles.",
      "Update /app/frontend/src/index.css tokens to match the semantic_tokens_hsl above (light + dark).",
      "Add Google Fonts import for Gloock + Manrope and set body font to Manrope.",
      "Implement mobile bottom tab bar + desktop top nav; ensure safe-area padding.",
      "Use Drawer for closet item detail and listing fee breakdown; Sheet for wizards and prompt presets.",
      "Add skeleton states for SAM-2 segmentation and Gemini responses.",
      "Ensure every interactive element and key info has data-testid attributes (kebab-case)."
    ],
    "recommended_custom_components_js": [
      {
        "name": "WaveformAudioPlayer.jsx",
        "why": "Phase 3 uses base64 MP3; provide a polished audio UI for stylist replies.",
        "behavior": "Play/pause, scrubber (Slider), time labels, transcript toggle; keyboard accessible.",
        "testids": [
          "stylist-reply-audio-player",
          "audio-player-play-button",
          "audio-player-scrubber"
        ]
      },
      {
        "name": "BottomTabs.jsx",
        "why": "Primary navigation on mobile.",
        "testids": [
          "bottom-tab-home",
          "bottom-tab-closet",
          "bottom-tab-stylist",
          "bottom-tab-market",
          "bottom-tab-me"
        ]
      },
      {
        "name": "SourceTagBadge.jsx",
        "why": "Consistent Private/Shared/Retail badges across closet + marketplace.",
        "testids": ["source-tag-badge"]
      }
    ],
    "libraries": [
      {
        "name": "framer-motion",
        "install": "npm i framer-motion",
        "use": "Button/card micro-interactions, drawer transitions, list entrance animations"
      },
      {
        "name": "recharts",
        "install": "npm i recharts",
        "use": "Admin charts (revenue, take-rate, users)"
      }
    ]
  }
}

---

<General UI UX Design Guidelines>  
    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms
    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text
   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json

 **GRADIENT RESTRICTION RULE**
NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc
NEVER use dark gradients for logo, testimonial, footer etc
NEVER let gradients cover more than 20% of the viewport.
NEVER apply gradients to text-heavy content or reading areas.
NEVER use gradients on small UI elements (<100px width).
NEVER stack multiple gradient layers in the same viewport.

**ENFORCEMENT RULE:**
    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors

**How and where to use:**
   • Section backgrounds (not content backgrounds)
   • Hero section header content. Eg: dark to light to dark color
   • Decorative overlays and accent elements only
   • Hero section with 2-3 mild color
   • Gradients creation can be done for any angle say horizontal, vertical or diagonal

- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**

</Font Guidelines>

- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. 
   
- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.

- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.
   
- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly
    Eg: - if it implies playful/energetic, choose a colorful scheme
           - if it implies monochrome/minimal, choose a black–white/neutral scheme

**Component Reuse:**
	- Prioritize using pre-existing components from src/components/ui when applicable
	- Create new components that match the style and conventions of existing components when needed
	- Examine existing components to understand the project's component patterns before creating new ones

**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component

**Best Practices:**
	- Use Shadcn/UI as the primary component library for consistency and accessibility
	- Import path: ./components/[component-name]

**Export Conventions:**
	- Components MUST use named exports (export const ComponentName = ...)
	- Pages MUST use default exports (export default function PageName() {...})

**Toasts:**
  - Use `sonner` for toasts"
  - Sonner component are located in `/app/src/components/ui/sonner.tsx`

Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.
</General UI UX Design Guidelines>
