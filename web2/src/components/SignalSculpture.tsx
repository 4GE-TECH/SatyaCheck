import { motion, useMotionValue, useMotionTemplate, useSpring, useReducedMotion } from 'motion/react';
import { useState } from 'react';
import { AudioLines, Fingerprint, MessageCircle } from 'lucide-react';
import { ease } from './UI';
export default function SignalSculpture() {
  const reduced = useReducedMotion();
  const x = useMotionValue(0), y = useMotionValue(0);
  const rx = useSpring(x, { stiffness: 100, damping: 22 });
  const ry = useSpring(y, { stiffness: 100, damping: 22 });
  const transform = useMotionTemplate`perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg)`;
  const [failed, setFailed] = useState(false);
  return <motion.div className="sculpture-stage" initial={{ opacity: 0, transform: reduced ? 'none' : 'translateY(24px) scale(.94)' }} animate={{ opacity: 1, transform: 'translateY(0) scale(1)' }} transition={{ duration: reduced ? 0 : 1.1, ease, delay: reduced ? 0 : .1 }}
    onPointerMove={event => { if (reduced || !matchMedia('(hover: hover) and (pointer: fine)').matches) return; const bounds = event.currentTarget.getBoundingClientRect(); x.set((event.clientY - bounds.top - bounds.height / 2) / bounds.height * -8); y.set((event.clientX - bounds.left - bounds.width / 2) / bounds.width * 10); }} onPointerLeave={() => { x.set(0); y.set(0); }}>
    <motion.div className="sculpture-object" style={{ transform: reduced ? 'none' : transform }} aria-hidden="true">
      {!failed ? <img src="/brand/signal-sculpture.png" alt="" width="1254" height="1254" onError={() => setFailed(true)}/> : <div className="sculpture-fallback"><i/><i/><i/></div>}
    </motion.div>
    <span className="orbit-tag identity"><Fingerprint size={15}/>Identity</span><span className="orbit-tag authenticity"><AudioLines size={15}/>Authenticity</span><span className="orbit-tag intent"><MessageCircle size={15}/>Intent</span>
    <span className="sculpture-caption"><i/>Three signals. One clearer picture.</span>
  </motion.div>;
}
