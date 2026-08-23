import {keycloak} from "./auth";import {wsUrl} from "./api";
type Handler=(event:Record<string,unknown>)=>void;
export class EventSocket{socket?:WebSocket;attempt=0;closed=false;handlers=new Set<Handler>();
 async connect(){await keycloak().updateToken(30);const accessToken=keycloak().token;if(this.closed||!accessToken)return;this.socket=new WebSocket(wsUrl(),["access_token",accessToken]);this.socket.onopen=()=>{this.attempt=0;this.socket?.send(JSON.stringify({op:"subscribe",events:["candle.*","smc.*","scenario.*","position.*","model.*","bandit.*"]}))};this.socket.onmessage=e=>{const value=JSON.parse(e.data);if(value.event_type)this.handlers.forEach(fn=>fn(value))};this.socket.onclose=()=>{if(!this.closed)setTimeout(()=>this.connect(),Math.min(30000,1000*2**this.attempt++))}}
 subscribe(fn:Handler){this.handlers.add(fn);return()=>this.handlers.delete(fn)}close(){this.closed=true;this.socket?.close()}}
