import Keycloak from "keycloak-js";

let instance: Keycloak | undefined;
let initialization: Promise<boolean> | undefined;

export function keycloak(): Keycloak {
  instance ??= new Keycloak({
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8080",
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "smart-money",
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "smart-money-api",
  });
  return instance;
}

export function initializeAuth(): Promise<boolean> {
  initialization ??= keycloak().init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false });
  return initialization;
}

export async function token(): Promise<string> {
  const client = keycloak();
  const authenticated = await initializeAuth();
  if (authenticated) await client.updateToken(30);
  return client.token ?? "";
}
