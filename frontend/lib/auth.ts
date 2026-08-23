import Keycloak from "keycloak-js";
let instance:Keycloak|undefined;
export function keycloak(){return instance??=new Keycloak({url:process.env.NEXT_PUBLIC_KEYCLOAK_URL??"http://localhost:8080",realm:"smart-money",clientId:"smart-money-api"})}
export async function token(){const kc=keycloak();await kc.updateToken(30);if(!kc.token)throw new Error("Not authenticated");return kc.token}
