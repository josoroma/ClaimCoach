/**
 * Type stub for the Hermes Desktop Plugin SDK surfaces ClaimCoach uses (US-1.4, PC-3).
 *
 * Checked by hand on 2026-10-30 against Hermes Agent v0.22.5:
 *   - ~/.hermes/hermes-agent/website/docs/developer-guide/desktop-plugin-sdk.md
 *     ("The plugin contract", "Contribution areas", "Plugin settings pages", "Calling it from the plugin")
 *   - ~/.hermes/hermes-agent/apps/desktop/src/api/plugins.ts (PluginRestOptions)
 * The canonical export list is apps/desktop/src/sdk/index.ts. Add a surface here only when
 * plugin.js starts using it, and cite the doc section it came from.
 */
declare module '@hermes/plugin-sdk' {
  import type { ReactNode } from 'react';

  export const PANES_AREA: 'panes';
  export const ROUTES_AREA: string;
  export const SIDEBAR_NAV_AREA: string;
  export const SETTINGS_PLUGINS_AREA: 'settings.plugins';
  export const STATUSBAR_AREAS: { readonly left: string; readonly right: string };

  /**
   * Capture a gateway file-save action before a REST read; call the action with the file's path on
   * the gateway and a suggested name to open the native save dialog. It never rejects
   * (desktop-plugin-sdk.md, "Mental model": `captureGatewayFileDownload()`; exported by
   * apps/desktop/src/sdk/index.ts). Older hosts lack it, so ClaimCoach feature-detects it (US-7.2).
   */
  export const captureGatewayFileDownload:
    | (() => (path: string, suggestedName: string) => Promise<void>)
    | undefined;

  export interface PluginRestOptions {
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    body?: unknown;
    upload?: { filename: string; contentType?: string; bytes: ArrayBuffer };
    timeoutMs?: number;
  }

  export interface PaneData {
    placement: 'main' | 'left' | 'right' | 'top' | 'bottom';
    dock?: { pane: string; pos: 'top' | 'bottom' | 'left' | 'right' | 'center' };
    width?: string;
    height?: string;
  }

  export interface RouteContribution {
    path: string;
  }

  export interface SidebarNavContribution {
    path: string;
    label: string;
    codicon: string;
  }

  export interface PluginContribution {
    /** Local id; the host namespaces it as `<plugin id>:<id>`. */
    id: string;
    area: string;
    title?: string;
    order?: number;
    when?: () => boolean;
    enabled?: boolean;
    render?: () => ReactNode;
    data?: PaneData | RouteContribution | SidebarNavContribution | Record<string, unknown>;
  }

  export interface PluginSettingsSubpage {
    id: string;
    title: string;
    render: () => ReactNode;
  }

  export interface PluginSettingsPage extends PluginSettingsSubpage {
    icon?: string;
    order?: number;
    children?: PluginSettingsSubpage[];
  }

  export interface PluginContext {
    readonly source: string;
    register: (contribution: PluginContribution) => () => void;
    registerMany: (contributions: PluginContribution[]) => () => void;
    /** Newer hosts only; feature-detect with `?.`. */
    registerSettingsPage?: (page: PluginSettingsPage) => () => void;
    rest: <T = unknown>(path: string, opts?: PluginRestOptions) => Promise<T>;
    /**
     * Gateway event stream by type, retired with the plugin ("The plugin contract"; "Pushing
     * events to your desktop half": `plugin.<id>.<event>` from `broadcast_plugin_event`).
     * Optional here because ClaimCoach feature-detects it (US-5.2).
     */
    onEvent?: (type: string, listener: (event: { payload?: unknown }) => void) => () => void;
    onDispose: (fn: () => void) => void;
  }

  export interface HermesPlugin {
    id: string;
    name?: string;
    description?: string;
    /** `false` ships the plugin opt-in (Capabilities → Plugins). */
    defaultEnabled?: boolean;
    register: (ctx: PluginContext) => void;
  }
}
