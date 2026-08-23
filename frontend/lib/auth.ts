import Keycloak from "keycloak-js";

let instance: Keycloak | undefined;

export function keycloak(): Keycloak {
  instance ??= new Keycloak({
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://localhost:8080",
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "smart-money",
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "smart-money-api",
  });
  return instance;
}

export async function token(): Promise<string> {
  const client = keycloak();
  await client.updateToken(30);
  return client.token ?? "";
}
