const products = {
  bed: ["Bed", 1.9, 2.12, .9],
  wardrobe: ["Wardrobe", 1.8, .62, 2.2],
  sofa: ["Sofa", 2.2, .92, .85],
  loveseat: ["Loveseat", 1.48, .85, .83],
  chair: ["Armchair", .86, .84, .83],
  rug: ["Rug", 2, 1.4, .018],
  nightstand: ["Nightstand", .48, .42, .53],
  table: ["Table", 1.4, .8, .75],
  shower: ["Shower", .9, .9, 2],
  bathtub: ["Bathtub", .75, 1.7, .56],
  sink: ["Sink", .62, .46, .84],
  vanity: ["Vanity", .8, .5, .86],
  toilet: ["Toilet", .38, .68, .8],
  fridge: ["Fridge", .83, .73, 1.8],
  fridge_2: ["2-door fridge", .83, .73, 1.8],
  fridge_4: ["4-door fridge", .92, .76, 1.83],
  dining_4: ["Dining set · 4 seats", 1.7, 1.85, .85],
  dining_6: ["Dining set · 6 seats", 2.72, 1.9, .86],
  dining_8: ["Dining set · 8 seats", 3.22, 2, .86],
  island: ["Kitchen island", 1.85, .98, .91],
  cabinets: ["Cabinets", 1.8, .61, .91],
  tv: ["TV", 1.2176, .07, .6849],
  console_floating: ["Floating TV console", 1.8, .42, .32],
  console_standing: ["Standing TV console", 1.8, .42, .52],
  coffee_table: ["Coffee table", 1.12, .6, .42],
  patio_set: ["Patio dining set", 1.74, 1.95, .85],
  lounge: ["Sun lounger", .71, 1.96, .8],
  planter: ["Planter", .55, .55, .98],
  car: ["Car", 4.5, 1.8, 1.48],
  tree: ["Tree", 2.5, 2.5, 3],
  cooktop: ["Cooktop", .6, .52, .045],
  bar_stools: ["Bar stools", 1.8, .45, 1.02],
  grill: ["Grill", 1.22, .59, 1.12],
  parasol: ["Patio umbrella", 2.45, 2.45, 2.25],
} as const;

export type ObjectKind = keyof typeof products;
export const objectName = (kind: ObjectKind) => products[kind][0];
export function dimensions(kind: ObjectKind) {
  const [,width,depth,height] = products[kind];
  return {width,depth,height};
}
export const objectKinds = Object.keys(products) as ObjectKind[];

export const furnitureRooms = [
  {name:"Living room", groups:[
    {name:"Seating", items:["sofa","loveseat","chair"]},
    {name:"Media & accents", items:["tv","console_floating","console_standing","rug","table","coffee_table"]},
  ], tip:"Leave room to walk past the seating and choose your TV by screen diagonal."},
  {name:"Bedroom", groups:[
    {name:"Sleep & storage", items:["bed","nightstand","wardrobe"]},
    {name:"Seating & rugs", items:["sofa","loveseat","rug"]},
  ], tip:"Use the bed frame dimensions and allow space to walk beside it and open the wardrobe."},
  {name:"Bathroom", groups:[
    {name:"Bath & shower", items:["shower","bathtub"]},
    {name:"Fixtures", items:["sink","vanity","toilet"]},
  ], tip:"Allow space in front of fixtures and keep the door swing clear."},
  {name:"Kitchen", groups:[
    {name:"Appliances", items:["fridge_2","fridge_4","cooktop"]},
    {name:"Dining sets", items:["dining_4","dining_6","dining_8"]},
    {name:"Worktops & storage", items:["island","cabinets","bar_stools"]},
  ], tip:"Dining footprints include chairs. Leave extra space to pull chairs out and open appliance doors."},
  {name:"Yard", groups:[
    {name:"Outdoor living", items:["patio_set","lounge","grill","car"]},
    {name:"Plants & shade", items:["planter","parasol","tree"]},
  ], tip:"Place items on a detected yard or balcony. Keep circulation and grill clearance in mind."},
] as const satisfies readonly {name:string;groups:readonly {name:string;items:readonly ObjectKind[]}[];tip:string}[];

export const yardKinds: ReadonlySet<ObjectKind> = new Set(furnitureRooms[4].groups.flatMap(group=>[...group.items]));
export const diningSeats = {dining_4:4,dining_6:6,dining_8:8,patio_set:4} as const;
export const tvSizeRange = {min:24,max:120};
export function tvDimensions(inches: number) {
  const unit = inches * .0254 / Math.hypot(16,9);
  return {width:16*unit,height:9*unit};
}
export function tvInches(width: number,height: number) {
  return Math.round(Math.hypot(width,height)/.0254);
}
