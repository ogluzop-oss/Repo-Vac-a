/**
 * Smart Manager AI — SDK oficial de JavaScript.
 *
 * Cliente ligero para la Enterprise REST API (`/api/v1`). Usa `fetch` (Node 18+ o navegador); se puede
 * inyectar un transporte para pruebas. Autenticación por JWT (`token`) o API Key (`apiKey` + `empresa`).
 * Soporta la convención de paginación/orden/filtrado (limit/offset/cursor/page/page_size/sort/order/
 * filters) e iteración por cursor (async iterator).
 *
 *   import { Client } from "@smartmanager/sdk";
 *   const c = new Client({ baseUrl, token });
 *   await c.communications.list({ limit: 20, sort: "fecha", order: "desc" });
 *   for await (const item of c.contacts.paginate({ q: "ana" })) { ... }
 *
 * La fuente de verdad de la API es su OpenAPI (`/api/v1/openapi.json`). Este SDK no la duplica.
 */

export const VERSION = "1.0.0";

export class SmartManagerError extends Error {
  constructor(message, { status = null, payload = null } = {}) {
    super(message);
    this.name = "SmartManagerError";
    this.status = status;
    this.payload = payload;
  }
}

class Resource {
  constructor(client, path) {
    this._client = client;
    this._path = path;
  }
  list(params = {}) {
    return this._client.request("GET", this._path, { params });
  }
  get(id, params = {}) {
    return this._client.request("GET", `${this._path}/${id}`, { params });
  }
  create(data) {
    return this._client.request("POST", this._path, { json: data });
  }
  async *paginate(params = {}) {
    const p = { limit: 100, ...params };
    for (;;) {
      const resp = await this._client.request("GET", this._path, { params: p });
      if (resp && typeof resp === "object" && Array.isArray(resp.data)) {
        for (const item of resp.data) yield item;
        if (!resp.next_cursor) return;
        p.cursor = resp.next_cursor;
      } else {
        for (const item of resp || []) yield item;
        return;
      }
    }
  }
}

const RECURSOS = {
  communications: "/communications",
  conversations: "/conversations",
  templates: "/templates",
  campaigns: "/campaigns",
  contacts: "/contacts",
  audit: "/audit/events",
  commerce: "/commerce",
  system: "/system",
};

export class Client {
  /**
   * @param {object} opts
   * @param {string} opts.baseUrl  Base de la API, p. ej. https://api.tu-dominio/api/v1
   * @param {string} [opts.token]  JWT (Authorization: Bearer)
   * @param {string} [opts.apiKey] API Key (X-API-Key)
   * @param {string} [opts.empresa] Tenant (X-Empresa-Id) para API Key
   * @param {function} [opts.transporte] (method, url, {params, json, headers}) => {status, body}
   * @param {number} [opts.timeout]
   */
  constructor({ baseUrl, token = null, apiKey = null, empresa = null, transporte = null, timeout = 20000 } = {}) {
    this.baseUrl = String(baseUrl || "").replace(/\/+$/, "");
    this.token = token;
    this.apiKey = apiKey;
    this.empresa = empresa;
    this._transporte = transporte;
    this._timeout = timeout;
    for (const [nombre, ruta] of Object.entries(RECURSOS)) {
      this[nombre] = new Resource(this, ruta);
    }
  }

  _headers() {
    const h = {
      "Content-Type": "application/json",
      Accept: "application/json",
      "User-Agent": `smartmanager-js/${VERSION}`,
    };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    else if (this.apiKey) h["X-API-Key"] = this.apiKey;
    if (this.empresa) h["X-Empresa-Id"] = String(this.empresa);
    return h;
  }

  _url(path, params) {
    let url = this.baseUrl + path;
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) {
      if (v !== undefined && v !== null) q.append(k, v);
    }
    const s = q.toString();
    return s ? `${url}?${s}` : url;
  }

  async request(method, path, { params = null, json = null } = {}) {
    const headers = this._headers();
    if (this._transporte) {
      const { status, body } = await this._transporte(method, this._url(path, params), {
        params,
        json,
        headers,
      });
      if (status && status >= 400) throw new SmartManagerError(`HTTP ${status}`, { status, payload: body });
      return body;
    }
    const resp = await fetch(this._url(path, params), {
      method,
      headers,
      body: json != null ? JSON.stringify(json) : undefined,
    });
    let body = null;
    try {
      body = await resp.json();
    } catch (_) {
      body = null;
    }
    if (!resp.ok) throw new SmartManagerError(`HTTP ${resp.status}`, { status: resp.status, payload: body });
    return body;
  }

  health() {
    return this.request("GET", "/system/health");
  }
}

export default { Client, SmartManagerError, VERSION };
