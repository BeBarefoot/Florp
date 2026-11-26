import {BoxGeometry, CanvasTexture, CylinderGeometry, DoubleSide, LatheGeometry, MeshStandardMaterial,
  RepeatWrapping, SphereGeometry, SRGBColorSpace, Vector2} from "three";
import {RoundedBoxGeometry} from "three/addons/geometries/RoundedBoxGeometry.js";
import {diningSeats} from "./furnitureCatalog";
import {itemBottom, type Item} from "./scene";

const palette = {
  oak: ["#aa774e",.63,0,"grain"], walnut:["#644530",.58,0,"grain"], black:["#252927",.58,.12],
  sage:["#747d68",.85,0,"weave"], linen:["#eee5d8",.9,0,"weave"], rust:["#ad6f55",.86,0,"weave"],
  rug:["#cab495",.95,0,"weave"], edge:["#b7a487",.96,0,"weave"], cream:["#e7e1d5",.53,0],
  ceramic:["#f0f0e9",.24,0], stone:["#b1a89a",.41,0], steel:["#aeb3b3",.34,.52],
  chrome:["#b4bfbd",.24,.63], glass:["#abdce0",.19,0], screen:["#171e21",.22,0],
  soil:["#46372b",1,0], pot:["#b97558",.79,0], leaf:["#64815b",.72,0], twig:["#596d47",.76,0],
} as const;
export type FurnitureFinish = keyof typeof palette;
export const furnitureColor = (finish: FurnitureFinish) => palette[finish][0];
type Shape = "box" | "soft" | "upholstered" | "sphere" | "tube" | "bowl" | "pot";
type XYZ = [number,number,number];
type Part = {position:XYZ;size:XYZ;finish:FurnitureFinish;shape:Shape;turn?:XYZ};

const geometries = {
  box:()=>new BoxGeometry(1,1,1),
  soft:()=>new RoundedBoxGeometry(1,1,1,2,.055),
  upholstered:()=>new RoundedBoxGeometry(1,1,1,2,.15),
  sphere:()=>new SphereGeometry(.5,16,10),
  tube:()=>new CylinderGeometry(.5,.5,1,20),
  bowl:()=>new LatheGeometry([[0,-.5],[.19,-.5],[.36,-.40],[.48,-.15],[.5,.35],[.49,.48],
    [.44,.5],[.41,.39],[.40,.1],[.30,-.26],[.16,-.36],[0,-.36]].map(([x,y])=>new Vector2(x,y)),32),
  pot:()=>new CylinderGeometry(.5,.35,1,20),
} satisfies Record<Shape,()=>import("three").BufferGeometry>;

function materialMap(style:"weave"|"grain"){
  const canvas=document.createElement("canvas");
  canvas.width=canvas.height=128;
  const context=canvas.getContext("2d")!;
  const image=context.createImageData(128,128);
  for(let y=0;y<128;y++)for(let x=0;x<128;x++){
    const noise=((x*271+y*313+x*y*37)%41)/41-.5;
    const tone=style==="weave"?232+noise*18+((x^y)&1)*12:
      226+14*Math.sin(y*Math.PI/8+Math.sin(x*Math.PI/32)*.7)+7*Math.cos(y*Math.PI/2)+noise*10;
    image.data.set([tone,tone,tone,255],4*(y*128+x));
  }
  context.putImageData(image,0,0);
  const texture=new CanvasTexture(canvas);
  texture.wrapS=texture.wrapT=RepeatWrapping;
  texture.repeat.set(2,2);
  texture.colorSpace=SRGBColorSpace;
  texture.anisotropy=4;
  return texture;
}

export function makeFurnitureResources(){
  const shapes=new Map<Shape,import("three").BufferGeometry>();
  const materials=new Map<FurnitureFinish,MeshStandardMaterial>();
  const maps=new Map<"weave"|"grain",CanvasTexture>();
  return {
    geometry(shape:Shape){
      let geometry=shapes.get(shape);
      if(!geometry){geometry=geometries[shape]();shapes.set(shape,geometry);}
      return geometry;
    },
    material(finish:FurnitureFinish,environment:import("three").Texture|null=null){
      let material=materials.get(finish);
      if(!material){
        const [color,roughness,metalness,style]=palette[finish];
        let map=style?maps.get(style):undefined;
        if(style&&!map){map=materialMap(style);maps.set(style,map);}
        material=new MeshStandardMaterial({color,roughness,metalness,map:map??null,
          ...(finish==="glass"?{transparent:true,opacity:.22,side:DoubleSide,depthWrite:false}:{})});
        materials.set(finish,material);
      }
      if(material.envMap!==environment){
        material.envMap=environment;
        material.envMapIntensity=.30;
        material.needsUpdate=true;
      }
      return material;
    },
    dispose(){
      shapes.forEach(geometry=>geometry.dispose());
      materials.forEach(material=>material.dispose());
      maps.forEach(texture=>texture.dispose());
    },
  };
}

export function furnitureParts(o:Item):Part[]{
  const parts:Part[]=[];
  const add=(x:number,y:number,z:number,w:number,h:number,d:number,finish:FurnitureFinish,shape:Shape="soft",turn?:XYZ)=>{
    parts.push({position:[x*o.width,y*o.height+itemBottom(o),z*o.depth],
      size:[w*o.width,h*o.height,d*o.depth],finish,shape,turn});
  };
  const legs=(x:number,z:number,top:number,finish:FurnitureFinish="walnut",width=.055,depth=.08)=>{
    for(const sx of [-x,x])for(const sz of [-z,z])add(sx,top/2,sz,width,top,depth,finish);
  };
  const chair=(x:number,z:number,w:number,d:number,front:number,outdoor:boolean,side=false)=>{
    const frame=outdoor?"black":"walnut";
    const offset=(u:number,v:number)=>side?[x+v*front,z+u]:[x+u,z+v*front];
    const piece=(u:number,y:number,v:number,a:number,h:number,b:number,finish:FurnitureFinish,shape?:Shape)=>{
      const [px,pz]=offset(u,v);
      add(px,y,pz,side?b:a,h,side?a:b,finish,shape);
    };
    for(const u of [-.37,.37])for(const v of [-.37,.37])piece(u*w,.25,v*d,w*.09,.5,d*.09,frame);
    piece(0,.52,0,w,.09,d,outdoor?"sage":"linen","upholstered");
    for(const u of [-.36,.36])piece(u*w,.74,-d*.43,w*.08,.48,d*.085,frame);
    piece(0,.88,-d*.42,w,.21,d*.14,outdoor?"oak":"walnut");
  };
  const cabinet=(finish:FurnitureFinish,panels:number,bodyBottom:number,bodyTop:number,stoneTop:boolean,top=1)=>{
    const bodyHeight=bodyTop-bodyBottom;
    const mid=(bodyBottom+bodyTop)/2;
    add(0,mid,-.02,.98,bodyHeight,.94,finish);
    for(let i=0;i<panels;i++){
      const x=(i+.5)/panels-.5;
      add(x,mid,.468,.96/panels,bodyHeight*.94,.057,finish);
      add(x,bodyTop-bodyHeight*.20,.48,.28/panels,Math.min(.024,.02/o.height),.039,"black");
    }
    add(0,(bodyTop+top)/2,0,1,top-bodyTop,1,stoneTop?"stone":finish);
  };
  const tap=(x:number,y:number,z:number)=>{
    add(x,y+.04,z,.04,.20,.044,"chrome","tube");
    add(x,y+.12,z+.065,.039,.026,.18,"chrome");
    add(x,y+.09,z+.14,.036,.065,.041,"chrome","tube");
  };

  if(Object.hasOwn(diningSeats,o.kind)){
    const seats=diningSeats[o.kind as keyof typeof diningSeats];
    const outdoor=o.kind==="patio_set";
    const endSeats=seats!==4;
    const tableW=endSeats?.67:.97;
    const tableD=.49;
    add(0,.852,0,tableW,.061,tableD,outdoor?"oak":"walnut");
    legs(tableW*.42,tableD*.38,.83,outdoor?"black":"walnut",.028,.037);
    const count=seats===8?3:2;
    const seatW=endSeats?.175:.26;
    for(let i=0;i<count;i++)for(const front of [-1,1]){
      chair((i-(count-1)/2)*tableW/(count+.28),-.365*front,seatW,.27,front,outdoor);
    }
    if(endSeats)for(const front of [-1,1])chair(-.414*front,0,.26,.172,front,outdoor,true);
    return parts;
  }

  switch(o.kind){
    case "car":
      add(0,.34,0,.99,.38,.96,"steel","upholstered");
      add(-.04,.64,0,.56,.26,.81,"screen","upholstered");
      add(-.04,.85,0,.37,.23,.72,"steel","upholstered");
      for(const x of [-.31,.31])for(const z of [-.43,.43])
        add(x,.18,z,.15,.36,.13,"black","tube",[Math.PI/2,0,0]);
      for(const z of [-.32,.32]){
        add(.47,.41,z,.055,.09,.20,"ceramic");
        add(-.47,.41,z,.055,.09,.20,"rust");
      }
      break;
    case "tree":
      add(0,.32,0,.09,.64,.09,"walnut","tube");
      add(0,.70,0,.70,.56,.76,"leaf","sphere");
      add(-.24,.69,.08,.51,.45,.56,"twig","sphere");
      add(.23,.76,-.09,.53,.46,.56,"leaf","sphere");
      add(.03,.85,-.06,.50,.30,.49,"sage","sphere");
      break;
    case "cooktop":
      add(0,.5,0,1,1,1,"screen");
      for(const x of [-.23,.23])for(const z of [-.22,.22]){
        add(x,1,z,.31,.1,.34,"steel","tube");
        add(x,1.06,z,.25,.1,.28,"black","tube");
      }
      break;
    case "bar_stools":
      for(const x of [-.375,-.125,.125,.375]){
        add(x,.035,0,.17,.07,.76,"steel","tube");
        add(x,.34,0,.023,.62,.11,"steel","tube");
        add(x,.50,.17,.12,.045,.13,"chrome");
        add(x,.69,0,.21,.11,.96,"oak","upholstered");
        add(x,.84,-.39,.20,.32,.16,"walnut","upholstered");
      }
      break;
    case "sofa":case "loveseat":case "chair": {
      const count=o.kind==="chair"?1:o.kind==="loveseat"?2:3;
      const fabric=o.kind==="chair"?"rust":"sage";
      legs(.40,.36,.14,"walnut");
      add(0,.33,0,.99,.41,.99,fabric,"upholstered");
      add(0,.68,-.395,.98,.63,.21,fabric,"upholstered");
      for(const x of [-.441,.441])add(x,.52,.055,.118,.53,.88,fabric,"upholstered");
      for(let i=0;i<count;i++){
        const x=((i+.5)/count-.5)*.77;
        add(x,.561,.088,.754/count,.19,.80,fabric,"upholstered");
        add(x,.747,-.273,.754/count,.494,.22,fabric,"upholstered",[-.14,0,0]);
      }
      if(count>1)add(.254,.73,-.19,.17,.31,.16,"linen","upholstered",[-.23,0,.13]);
      break;
    }
    case "bed": {
      legs(.42,.39,.16);
      add(0,.245,.008,1,.27,.984,"oak");
      add(0,.59,-.473,1,.82,.054,"oak");
      const w=(o.mattressWidth??o.width*.95)/o.width,d=(o.mattressDepth??o.depth*.94)/o.depth;
      add(0,.48,.018,w,.24,d,"linen","upholstered");
      add(0,.61,.123,w*.99,.064,d*.75,"sage","upholstered");
      add(0,.647,.281,w,.049,d*.33,"linen","upholstered");
      for(const x of [-.224,.224])add(x*w,.643,-d*.346,w*.415,.135,d*.204,"linen","upholstered");
      break;
    }
    case "table":case "coffee_table":
      legs(.407,.377,.93);
      add(0,.954,0,1,.092,1,"oak");
      if(o.kind==="coffee_table")add(0,.295,0,.85,.061,.81,"walnut");
      break;
    case "rug":
      add(0,.42,0,1,.84,1,"edge","upholstered");
      add(0,.66,0,.91,.68,.911,"rug","upholstered");
      break;
    case "wardrobe":
      cabinet("oak",3,.03,.987,false);
      break;
    case "nightstand":case "console_floating":case "console_standing":
      if(o.kind!=="console_floating")legs(.39,.32,.25);
      cabinet("oak",o.kind==="nightstand"?2:3,o.kind==="console_floating"?0:.22,.94,false);
      break;
    case "island":case "cabinets":
      add(0,.051,-.039,.92,.102,.80,"walnut");
      cabinet(o.kind==="island"?"oak":"cream",3,.09,.934,true);
      break;
    case "fridge":case "fridge_2":case "fridge_4": {
      add(0,.501,-.042,.98,.978,.905,"black");
      const rows=o.kind==="fridge_4"?[[.744,.493],[.255,.479]]:[[.658,.676],[.16,.303]];
      const columns=o.kind==="fridge_4"?[-.252,.252]:[0];
      for(const [y,h] of rows)for(const x of columns){
        add(x,y,.441,columns.length===1?1:.488,h,.116,"steel");
        const handle=columns.length===1?-.37:x*.34;
        add(handle,y+.017,.478,.036,h*.49,.039,"black");
      }
      break;
    }
    case "tv":
      add(0,.5,-.20,1,1,.6,"black");
      add(0,.5,.105,.974,.956,.12,"screen");
      add(0,.023,.107,.028,.009,.13,"steel");
      break;
    case "toilet":
      add(0,.22,.12,.66,.44,.57,"ceramic","upholstered");
      add(0,.49,.121,.98,.39,.753,"ceramic","bowl");
      add(0,.73,-.318,.88,.51,.35,"ceramic");
      add(0,.992,-.316,.14,.012,.12,"chrome","tube");
      break;
    case "shower":
      add(0,.019,0,1,.038,1,"stone");
      add(-.479,.515,0,.032,.956,.97,"glass","box");
      add(0,.515,-.479,.94,.956,.032,"glass","box");
      for(const [x,z] of [[-.48,-.48],[-.48,.48],[.48,-.48]])add(x,.51,z,.035,.98,.035,"chrome");
      add(-.334,.612,-.429,.03,.56,.032,"chrome","tube");
      add(-.334,.896,-.332,.038,.022,.214,"chrome");
      add(-.334,.884,-.216,.21,.025,.21,"chrome","tube");
      add(0,.04,.09,.126,.003,.126,"chrome","tube");
      break;
    case "bathtub":
      add(0,.5,-.02,1,1,.96,"ceramic","bowl");
      tap(.27,.785,.4);
      break;
    case "sink":case "vanity":
      if(o.kind==="vanity")cabinet("oak",2,.06,.68,true,.74);
      else add(0,.358,-.02,.34,.716,.48,"ceramic","pot");
      add(0,.86,.026,1,.28,.95,"ceramic","bowl");
      tap(0,.846,-.33);
      break;
    case "lounge":
      legs(.37,.35,.43,"black");
      add(0,.45,0,1,.10,.97,"oak");
      add(0,.524,.158,.89,.09,.656,"linen","upholstered");
      add(0,.724,-.301,.89,.092,.44,"linen","upholstered",[.35,0,0]);
      break;
    case "planter":
      add(0,.195,0,.96,.39,.96,"pot","pot");
      add(0,.39,0,.84,.025,.84,"soil","tube");
      for(let i=0;i<9;i++){
        const angle=i*2.4,r=i===0?0:.28+i%3*.052;
        const x=Math.cos(angle)*r,z=Math.sin(angle)*r;
        add(x*.45,.527,z*.45,.037,.28,.037,"twig","tube",[z*.45,0,-x*.45]);
        add(x,.64+(i%4)*.06,z,.22,.31,.22,i%2?"leaf":"twig","sphere",[z,0,-x]);
      }
      break;
    case "grill":
      legs(.4,.32,.68,"black");
      add(0,.25,0,.8,.055,.81,"steel");
      add(0,.73,0,.99,.26,1,"black");
      add(0,.886,-.03,.94,.223,.91,"steel","upholstered");
      add(0,.856,.455,.53,.048,.091,"black");
      for(const x of [-.23,0,.23])add(x,.71,.493,.07,.066,.024,"steel");
      break;
    case "parasol":
      add(0,.036,0,.19,.072,.19,"stone","tube");
      add(0,.49,0,.023,.94,.023,"walnut","tube");
      add(0,.925,0,1,.15,1,"linen","sphere");
      break;
  }
  return parts;
}
