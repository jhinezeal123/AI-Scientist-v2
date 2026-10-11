/** T3's terminal interaction contract, rendered with xterm in Workbench. */
import {useEffect,useRef,useState} from 'react';
import {Terminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import type {ProviderAuthResponse} from '../../bridge/contracts';

export default function ProviderAuthTerminal({output,outputOffset,onResponse}:{output:string;outputOffset?:number;onResponse:(response:Extract<ProviderAuthResponse,{type:'terminal'}>)=>void}){
  const mount=useRef<HTMLDivElement>(null),surface=useRef<Terminal|null>(null),written=useRef(0),latest=useRef(onResponse);latest.current=onResponse;
  const [error,setError]=useState('');
  useEffect(()=>{if(!mount.current)return;const terminal=new Terminal({fontSize:13,convertEol:true,theme:{background:'#151918',foreground:'#d7dfd9'}}),fit=new FitAddon();terminal.loadAddon(fit);terminal.open(mount.current);surface.current=terminal;
    const observer=new ResizeObserver(()=>{try{fit.fit();}catch{setError('Could not fit the terminal.');}});observer.observe(mount.current);
    const input=terminal.onData(data=>latest.current({type:'terminal',data})),resize=terminal.onResize(({cols,rows})=>latest.current({type:'terminal',data:'',size:{cols,rows}}));
    terminal.write(output);written.current=outputOffset??output.length;
    return()=>{observer.disconnect();input.dispose();resize.dispose();terminal.dispose();surface.current=null;};
  },[]);
  useEffect(()=>{const delta=(outputOffset??output.length)-written.current;if(delta>0){surface.current?.write(delta<=output.length?output.slice(-delta):output);written.current=outputOffset??output.length;}},[output,outputOffset]);
  return <><div ref={mount} aria-label="Provider sign-in terminal" className="relative h-64 overflow-hidden rounded-md border border-border"/>{error&&<p role="alert" className="text-destructive">{error}</p>}</>;
}
