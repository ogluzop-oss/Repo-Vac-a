// Ejemplo de arranque del SDK de JavaScript de Smart Manager AI.
// Ejecuta:  node quickstart.mjs
// Requiere SM_BASE_URL y SM_TOKEN (o SM_API_KEY + SM_EMPRESA).

import { Client, SmartManagerError } from "@smartmanager/sdk";

const baseUrl = process.env.SM_BASE_URL || "https://api.tu-dominio/api/v1";
const c = process.env.SM_TOKEN
  ? new Client({ baseUrl, token: process.env.SM_TOKEN })
  : new Client({ baseUrl, apiKey: process.env.SM_API_KEY, empresa: process.env.SM_EMPRESA });

try {
  console.log("Salud:", await c.health());
  const pagina = await c.communications.list({ limit: 10, sort: "fecha", order: "desc" });
  console.log("Comunicaciones (página):", pagina);
  for await (const contacto of c.contacts.paginate({ q: "ana" })) {
    console.log("Contacto:", contacto);
  }
} catch (e) {
  if (e instanceof SmartManagerError) console.error("Error de API:", e.message, "status:", e.status);
  else throw e;
}
