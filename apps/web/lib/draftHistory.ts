import {useCallback,useReducer} from 'react';
import type {Geometry} from './api';
export type History={past:Geometry[];present:Geometry|null;future:Geometry[];group:Geometry|null};
export type Action={type:'set';value:Geometry|null|((g:Geometry|null)=>Geometry|null)}|{type:'reset';value:Geometry|null}|{type:'undo'|'redo'|'begin'|'end'};
export const emptyHistory:History={past:[],present:null,future:[],group:null};
export function draftHistory(state:History,action:Action):History{
 if(action.type==='reset')return {...emptyHistory,present:action.value};
 if(action.type==='begin')return {...state,group:state.present};
 if(action.type==='end')return state.group&&state.group!==state.present?{...state,past:[...state.past,state.group].slice(-100),group:null}: {...state,group:null};
 if(action.type==='undo'){
  if(!state.past.length||!state.present||state.group)return state;
  return {past:state.past.slice(0,-1),present:state.past[state.past.length-1],future:[state.present,...state.future],group:null};
 }
 if(action.type==='redo'){
  if(!state.future.length||!state.present||state.group)return state;
  return {past:[...state.past,state.present].slice(-100),present:state.future[0],future:state.future.slice(1),group:null};
 }
 if(action.type!=='set')return state;
 const next=typeof action.value==='function'?action.value(state.present):action.value;
 if(next===state.present)return state;
 return {...state,present:next,future:[],past:state.present&&!state.group?[...state.past,state.present].slice(-100):state.past};
}
export function useDraftHistory(){
 const [state,dispatch]=useReducer(draftHistory,emptyHistory);
 const set=useCallback((value:Extract<Action,{type:'set'}>['value'])=>dispatch({type:'set',value}),[]);
 const reset=useCallback((value:Geometry|null)=>dispatch({type:'reset',value}),[]);
 return {geometry:state.present,setGeometry:set,resetGeometry:reset,canUndo:state.past.length>0,canRedo:state.future.length>0,
  undo:()=>dispatch({type:'undo'}),redo:()=>dispatch({type:'redo'}),begin:()=>dispatch({type:'begin'}),end:()=>dispatch({type:'end'})};
}
