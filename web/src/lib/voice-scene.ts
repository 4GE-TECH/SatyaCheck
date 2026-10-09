/** Local, procedural 3D brand model. No assets, network requests or runtime dependencies. */
type Vec = [number, number, number];
const pearl: Vec = [0.82, 0.84, 1];
const indigo: Vec = [0.27, 0.19, 0.86];
const violet: Vec = [0.64, 0.53, 1];

const vertex = `
attribute vec3 a_position; attribute vec3 a_normal; attribute vec3 a_color;
uniform vec2 u_angle; uniform float u_aspect;
varying vec3 v_normal; varying vec3 v_color; varying vec3 v_position;
void main() {
  float cx=cos(u_angle.x), sx=sin(u_angle.x), cy=cos(u_angle.y), sy=sin(u_angle.y);
  mat3 rotation=mat3(cy,0.,-sy, 0.,1.,0., sy,0.,cy)*mat3(1.,0.,0., 0.,cx,sx, 0.,-sx,cx);
  vec3 p=rotation*a_position;
  float distance=5.8-p.z;
  gl_Position=vec4(p.x*2.7/u_aspect,p.y*2.7,1.01*distance-0.201,distance);
  v_normal=rotation*a_normal; v_color=a_color; v_position=p;
}`;
const fragment = `
precision mediump float;
varying vec3 v_normal; varying vec3 v_color; varying vec3 v_position;
void main() {
  vec3 n=normalize(v_normal), l=normalize(vec3(-2.,3.,4.));
  vec3 eye=normalize(vec3(0.,0.,5.8)-v_position);
  float diffuse=max(0.,dot(n,l));
  float rim=pow(1.-max(0.,dot(n,eye)),3.);
  float specular=pow(max(0.,dot(n,normalize(l+eye))),48.);
  vec3 color=v_color*(.38+.7*diffuse)+vec3(.63,.68,1.)*rim*.35+specular*.45;
  gl_FragColor=vec4(color,1.);
}`;

function geometry() {
  const vertices: number[] = [];
  function triangle(a: Vec, b: Vec, c: Vec, color: Vec) {
    const u = b.map((value, i) => value - a[i]);
    const v = c.map((value, i) => value - a[i]);
    const n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
    const length = Math.hypot(...n) || 1;
    for (const point of [a, b, c]) vertices.push(...point, ...n.map(value => value / length), ...color);
  }
  const outline = [[0,1.22],[-1.02,.85],[-.94,-.28],[-.58,-.88],[0,-1.3],[.58,-.88],[.94,-.28],[1.02,.85]];
  function shield(scale: number, back: number, front: number, color: Vec) {
    for (let i = 0; i < outline.length; i++) {
      const next = (i + 1) % outline.length;
      const point = (index: number, radius: number, z: number): Vec => [outline[index][0]*scale*radius,outline[index][1]*scale*radius,z];
      const a=point(i,1,back), b=point(next,1,back), c=point(next,.88,front), d=point(i,.88,front);
      triangle(a,b,c,color); triangle(a,c,d,color);
      triangle([0,0,front],d,c,color);
      triangle([0,0,back],b,a,color);
    }
  }
  shield(1.03,-.22,.16,pearl);
  shield(.8,.17,.3,indigo);
  // Raised waveform is modeled geometry, never an illustrative audio measurement.
  const heights = [.18,.38,.62,.9,1.12,.78,.52,.3,.16];
  heights.forEach((height, i) => {
    const x = (i-4)*.116, w=.038, y=-.05, z=.32, depth=.055;
    const a: Vec=[x-w,y-height/2,z], b: Vec=[x+w,y-height/2,z], c: Vec=[x+w,y+height/2,z], d: Vec=[x-w,y+height/2,z];
    triangle(a,b,c,pearl); triangle(a,c,d,pearl);
    triangle(b,[b[0],b[1],z-depth],[c[0],c[1],z-depth],violet); triangle(b,[c[0],c[1],z-depth],c,violet);
  });
  function tube(tilt: number, turn: number, color: Vec) {
    const rotate = ([x,y,z]: Vec): Vec => {
      const ty=y*Math.cos(tilt)-z*Math.sin(tilt), tz=y*Math.sin(tilt)+z*Math.cos(tilt);
      return [x*Math.cos(turn)-ty*Math.sin(turn),x*Math.sin(turn)+ty*Math.cos(turn),tz];
    };
    const point=(i:number,j:number):Vec => {
      const a=i/80*Math.PI*2, b=j/6*Math.PI*2;
      return rotate([(1.72+.017*Math.cos(b))*Math.cos(a),(1.72+.017*Math.cos(b))*Math.sin(a),.017*Math.sin(b)]);
    };
    for(let i=0;i<80;i++) for(let j=0;j<6;j++) {
      triangle(point(i,j),point(i+1,j),point(i+1,j+1),color);
      triangle(point(i,j),point(i+1,j+1),point(i,j+1),color);
    }
    // Each orbit carries a small faceted node, representing one of the three signals.
    const center=rotate([1.72,0,0]);
    const axes:Vec[]=[[.095,0,0],[-.095,0,0],[0,.095,0],[0,-.095,0],[0,0,.095],[0,0,-.095]];
    const at=(i:number):Vec => axes[i].map((value,k)=>value+center[k]) as Vec;
    for(const face of [[0,2,4],[2,1,4],[1,3,4],[3,0,4],[2,0,5],[1,2,5],[3,1,5],[0,3,5]]) triangle(at(face[0]),at(face[1]),at(face[2]),pearl);
  }
  tube(.92,.35,[.45,.43,.83]); tube(-.95,-.4,[.6,.57,.94]); tube(.3,1.1,[.31,.3,.65]);
  return new Float32Array(vertices);
}

export function createVoiceScene(canvas: HTMLCanvasElement) {
  const gl = canvas.getContext('webgl', { alpha: true, antialias: true, powerPreference: 'low-power' });
  if (!gl) return null;
  const shaders: WebGLShader[] = [];
  let program: WebGLProgram | null = null;
  let buffer: WebGLBuffer | null = null;
  try {
    const compile=(type:number, source:string) => {
      const shader=gl.createShader(type);
      if(!shader) throw new Error('Could not allocate a shader');
      shaders.push(shader); gl.shaderSource(shader,source); gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) throw new Error('Could not compile the brand model');
      return shader;
    };
    program=gl.createProgram(); buffer=gl.createBuffer();
    if(!program || !buffer) throw new Error('Could not allocate the brand model');
    gl.attachShader(program,compile(gl.VERTEX_SHADER,vertex)); gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragment));
    gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error('Could not link the brand model');
    gl.useProgram(program);
    const data=geometry(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer); gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
    for(const [i,name] of ['a_position','a_normal','a_color'].entries()) {
      const location=gl.getAttribLocation(program,name); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location,3,gl.FLOAT,false,36,i*12);
    }
    const angle=gl.getUniformLocation(program,'u_angle'), aspect=gl.getUniformLocation(program,'u_aspect');
    gl.enable(gl.DEPTH_TEST); gl.clearColor(0,0,0,0);
    return {
      draw(time:number, x:number, y:number) {
        const dpr=Math.min(window.devicePixelRatio || 1,1.5);
        const width=Math.max(1,Math.round(canvas.clientWidth*dpr)), height=Math.max(1,Math.round(canvas.clientHeight*dpr));
        if(canvas.width!==width || canvas.height!==height) { canvas.width=width; canvas.height=height; }
        gl.viewport(0,0,width,height); gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
        gl.uniform2f(angle,-.12+y*.13+Math.sin(time*.45)*.04,.3+x*.25+Math.sin(time*.3)*.14);
        gl.uniform1f(aspect,width/height); gl.drawArrays(gl.TRIANGLES,0,data.length/9);
      },
      dispose() { for(const shader of shaders) gl.deleteShader(shader); gl.deleteBuffer(buffer); gl.deleteProgram(program); },
    };
  } catch (error) {
    console.warn('SatyaCheck brand model unavailable', error);
    for(const shader of shaders) gl.deleteShader(shader);
    if(buffer) gl.deleteBuffer(buffer); if(program) gl.deleteProgram(program);
    return null;
  }
}
