import {useEffect, useRef} from "react";
import {useThree} from "@react-three/fiber";
import {Mesh, Raycaster, Vector2} from "three";
import type {Item} from "../../lib/plan/scene";

export function WalkthroughObjects({onHover, onTap}: {
  onHover: (id: string) => void;
  onTap: (id: string) => void;
}) {
  const {gl, get} = useThree();
  const callbacks = useRef({onHover, onTap});
  callbacks.current = {onHover, onTap};
  useEffect(() => {
    const canvas = gl.domElement;
    const ray = new Raycaster();
    const pointer = new Vector2();
    let press: {id: number; x: number; y: number} | null = null;
    function pick(event: PointerEvent) {
      const bounds = canvas.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return "";
      pointer.set(2 * (event.clientX - bounds.left) / bounds.width - 1,
        1 - 2 * (event.clientY - bounds.top) / bounds.height);
      const {camera, scene} = get();
      camera.updateMatrixWorld();
      ray.setFromCamera(pointer, camera);
      const hit = ray.intersectObjects(scene.children, true).find(({object}) =>
        object instanceof Mesh && object.visible &&
        (object.userData.openingId || (!object.userData.glass &&
        (object.userData.maskId || object.userData.pickFixtureId))));
      if(hit?.object.userData.openingId) return "opening:"+hit.object.userData.openingId;
      return (hit?.object.userData.furnitureId ?? hit?.object.userData.pickFixtureId ?? "") as string;
    }
    function move(event: PointerEvent) {
      if (event.pointerType !== "mouse" || event.buttons) return;
      const id = pick(event);
      // Keep the action bar available as the pointer moves to its buttons.
      if (id) callbacks.current.onHover(id);
    }
    function down(event: PointerEvent) {
      if (event.button === 0 && event.isPrimary)
        press = {id: event.pointerId, x: event.clientX, y: event.clientY};
      else press = null;
    }
    function up(event: PointerEvent) {
      if (!press || press.id !== event.pointerId) return;
      const isTap = Math.hypot(press.x - event.clientX, press.y - event.clientY) < 6;
      press = null;
      if (isTap) {
        const id = pick(event);
        callbacks.current.onTap(id);
        if (id) event.preventDefault();
      }
    }
    function cancel() {
      press = null;
    }
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", up, true);
    canvas.addEventListener("pointercancel", cancel);
    return () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", up, true);
      canvas.removeEventListener("pointercancel", cancel);
    };
  }, [gl, get]);
  return null;
}

export function ObjectHighlight({item, scale}: {item: Item; scale: number}) {
  return <group position={[item.position.x * scale, 0, item.position.y * scale]}
    rotation={[0, -item.rotation * Math.PI / 180, 0]}>
    <mesh position={[0, .012, 0]} raycast={()=>{}}>
      <boxGeometry args={[item.width + .05, .014, item.depth + .05]}/>
      <meshBasicMaterial color="#b99055" transparent opacity={.5} depthWrite={false}/>
    </mesh>
  </group>;
}
