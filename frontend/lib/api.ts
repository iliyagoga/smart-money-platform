import {token} from "./auth";
const base=process.env.NEXT_PUBLIC_API_URL??"http://localhost:8050";
export async function api<T>(path:string,init:RequestInit={}):Promise<T>{const response=await fetch(base+path,{...init,headers:{"Content-Type":"application/json",Authorization:`Bearer ${await token()}`,...init.headers},cache:"no-store"});if(!response.ok)throw new Error(`${response.status}: ${await response.text()}`);return response.json()}
export function wsUrl(){return base.replace(/^http/,"ws")+"/ws"}
