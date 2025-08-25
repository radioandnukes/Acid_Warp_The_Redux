# acid_warp_gl.py (chaos edition)
import sys, time, math, random
import glfw
from OpenGL.GL import *

VERT_SRC = r"""
#version 330 core
out vec2 vUV;
void main() {
    vec2 pos = vec2((gl_VertexID==2)? 3.0 : -1.0,
                    (gl_VertexID==1)? 3.0 : -1.0);
    gl_Position = vec4(pos, 0.0, 1.0);
    vUV = 0.5 * (pos + 1.0);
}
"""

FRAG_SRC = r"""
#version 330 core
in vec2 vUV;
out vec4 FragColor;

uniform vec2  iResolution;
uniform float iTime;
uniform int   effect;
uniform float speed;
uniform int   palette;
uniform float paletteShift;
uniform vec3  rgbGain;

const float PI = 3.14159265359;

// ---- Palettes ----
vec3 palette_rainbow(float t){
    vec3 a=vec3(0.5), b=vec3(0.5), c=vec3(1.0), d=vec3(0.0,0.33,0.67);
    return a + b*cos(2.0*PI*(c*t + d));
}
vec3 palette_fire(float t){ return clamp(vec3(0.2,0.1,0.0) + vec3(1.0,0.5,0.0)*pow(t,1.5), 0.0, 1.0); }
vec3 palette_ice(float t){ return clamp(vec3(0.0,0.1,0.2) + vec3(0.3,0.6,1.0)*t, 0.0, 1.0); }
vec3 palette_slime(float t){
    vec3 a=vec3(0.05,0.2,0.03), b=vec3(0.0,0.8,0.1);
    return clamp(a + b*(0.5 + 0.5*cos(2.0*PI*(vec3(1.0)*t + vec3(0.2,0.4,0.6)))), 0.0, 1.0);
}
vec3 palette_gray(float t){ return vec3(t); }

vec3 pick_palette(int p, float t){
    t = fract(t);
    if (p==1) return palette_fire(t);
    if (p==2) return palette_ice(t);
    if (p==3) return palette_slime(t);
    if (p==4) return palette_gray(t);
    return palette_rainbow(t);
}

// ---- Patterns ----
float pat_plasma(vec2 p, float t){
    float v = 0.0;
    v += sin(p.x*3.0 + t*1.2);
    v += sin(p.y*3.5 + t*1.7);
    v += sin((p.x+p.y)*4.0 - t*1.1);
    v += sin(length(p)*6.0 - t*2.2);
    return 0.5 + 0.5*(v/4.0);
}
float pat_rings(vec2 p, float t){ return 0.5 + 0.5*sin(10.0*length(p) - 3.0*t); }
float pat_swirl(vec2 p, float t){ return 0.5 + 0.5*sin(10.0*atan(p.y,p.x) + 6.0*length(p) - 2.0*t); }
float pat_xor(vec2 p, float t){
    vec2 g = floor((p*64.0) + vec2(64.0));
    int x = (int(g.x) ^ int(g.y)) & 255;
    float v = float(x)/255.0;
    return fract(v + 0.15*sin(atan(p.y,p.x)*4.0 + t));
}
float pat_tunnel(vec2 p, float t){
    float a = atan(p.y, p.x), r = length(p);
    float z = 0.25/(r+0.001) + 0.25*a/PI + 0.3*t;
    return fract(z);
}
float pat_mandel(vec2 p, float t){
    vec2 c = p*1.8 + vec2(-0.5 + 0.2*sin(t*0.2), 0.2*cos(t*0.17));
    vec2 z = vec2(0.0);
    int iters = 64; float i;
    for(i=0.0; i<float(iters); i++){
        vec2 z2 = vec2(z.x*z.x - z.y*z.y, 2.0*z.x*z.y) + c;
        z = z2;
        if(dot(z,z) > 4.0) break;
    }
    return pow(i/float(iters), 0.7);
}

void main(){
    vec2 uv = gl_FragCoord.xy / iResolution.xy;
    vec2 p = (uv - 0.5) * vec2(iResolution.x/iResolution.y, 1.0);
    float t = iTime;

    float v = 0.0;
    if      (effect==0) v = pat_plasma(p, t);
    else if (effect==1) v = pat_rings(p, t);
    else if (effect==2) v = pat_swirl(p, t);
    else if (effect==3) v = pat_xor(p, t);
    else if (effect==4) v = pat_tunnel(p, t);
    else                v = pat_mandel(p, t);

    vec3 col = pick_palette(palette, v + paletteShift);
    col *= rgbGain;                 // channel chaos
    col = clamp(col, 0.0, 1.0);     // keep it display-safe
    FragColor = vec4(col, 1.0);
}
"""

EFFECT_NAMES = ["Plasma", "Rings", "Swirl", "XOR Candy", "Tunnel", "Mandel-ish"]
PALETTE_NAMES = ["Rainbow", "Fire", "Ice", "Slime", "Gray"]

def gl_compile(src, kind):
    h = glCreateShader(kind); glShaderSource(h, src); glCompileShader(h)
    if not glGetShaderiv(h, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(h).decode())
    return h

def gl_link(vs, fs):
    p = glCreateProgram()
    glAttachShader(p, vs); glAttachShader(p, fs); glLinkProgram(p)
    if not glGetProgramiv(p, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(p).decode())
    glDetachShader(p, vs); glDetachShader(p, fs)
    glDeleteShader(vs); glDeleteShader(fs)
    return p

class State:
    def __init__(self):
        # core
        self.effect = 0
        self.palette = 0
        self.speed = 1.0
        self.shift = 0.0
        self.paused = False

        # chaos flags
        self.auto_roll = False
        self.chaos_rgb = False
        self.chaos_palette = False
        self.chaos_effect = False

        # chaos params
        self.roll_rate = 0.08                 # palette shift per second
        self.rgb_gain = [1.0, 1.0, 1.0]
        self.next_rgb_change = 0.0
        self.next_palette_change = 0.0
        self.next_effect_change = 0.0

        self.last_report = 0.0

    def report(self, force=False):
        now = time.time()
        if force or now - self.last_report > 0.15:
            self.last_report = now
            print(f"[{EFFECT_NAMES[self.effect]}]  Pal:{PALETTE_NAMES[self.palette]}  "
                  f"Speed:{self.speed:.2f} Shift:{self.shift:.2f}  "
                  f"Roll:{self.auto_roll} RGB:{self.chaos_rgb} PalRnd:{self.chaos_palette} EffRnd:{self.chaos_effect}")

def main():
    if not glfw.init():
        print("GLFW init failed"); sys.exit(1)

    # macOS core profile
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)

    win = glfw.create_window(1280, 720, "Acid Warp (Python + OpenGL) — Chaos", None, None)
    if not win:
        glfw.terminate(); print("Window create failed"); sys.exit(1)
    glfw.make_context_current(win)
    glfw.swap_interval(1)

    random.seed()

    vs = gl_compile(VERT_SRC, GL_VERTEX_SHADER)
    fs = gl_compile(FRAG_SRC, GL_FRAGMENT_SHADER)
    prog = gl_link(vs, fs)
    glUseProgram(prog)

    vao = glGenVertexArrays(1); glBindVertexArray(vao)

    # uniforms
    loc_iRes   = glGetUniformLocation(prog, "iResolution")
    loc_iTime  = glGetUniformLocation(prog, "iTime")
    loc_effect = glGetUniformLocation(prog, "effect")
    loc_speed  = glGetUniformLocation(prog, "speed")
    loc_pal    = glGetUniformLocation(prog, "palette")
    loc_shift  = glGetUniformLocation(prog, "paletteShift")
    loc_gain   = glGetUniformLocation(prog, "rgbGain")

    st = State()
    t_sim = 0.0
    last = time.time()

    def schedule_rgb(now):
        st.next_rgb_change = now + random.uniform(0.25, 2.5)

    def schedule_palette(now):
        st.next_palette_change = now + random.uniform(1.5, 4.5)

    def schedule_effect(now):
        st.next_effect_change = now + random.uniform(2.0, 6.0)

    def rand_gain():
        # 0.6–1.6 with occasional punchy extremes
        base = [random.uniform(0.6, 1.6) for _ in range(3)]
        if random.random() < 0.12:
            base[random.randrange(3)] *= random.uniform(1.8, 2.4)
        return [max(0.0, min(3.0, g)) for g in base]

    def on_key(win, key, sc, action, mods):
        if action not in (glfw.PRESS, glfw.REPEAT): return
        if key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(win, True)
        elif key == glfw.KEY_SPACE:
            st.paused = not st.paused; st.report(True)
        elif key in (glfw.KEY_1, glfw.KEY_2, glfw.KEY_3, glfw.KEY_4, glfw.KEY_5, glfw.KEY_6):
            st.effect = key - glfw.KEY_1; st.report(True)
        elif key == glfw.KEY_RIGHT:
            st.effect = (st.effect + 1) % 6; st.report(True)
        elif key == glfw.KEY_LEFT:
            st.effect = (st.effect - 1) % 6; st.report(True)
        elif key == glfw.KEY_UP:
            st.speed = max(0.05, st.speed + 0.05); st.report(True)
        elif key == glfw.KEY_DOWN:
            st.speed = max(0.05, st.speed - 0.05); st.report(True)
        elif key == glfw.KEY_A:
            st.palette = (st.palette + 1) % 5; st.report(True)
        elif key == glfw.KEY_Z:
            st.palette = (st.palette - 1) % 5; st.report(True)
        elif key == glfw.KEY_LEFT_BRACKET:
            st.shift -= 0.02; st.report(True)
        elif key == glfw.KEY_RIGHT_BRACKET:
            st.shift += 0.02; st.report(True)

        # chaos toggles
        elif key == glfw.KEY_R:
            st.auto_roll = not st.auto_roll; st.report(True)
        elif key == glfw.KEY_C:
            st.chaos_rgb = not st.chaos_rgb
            schedule_rgb(time.time()); st.report(True)
        elif key == glfw.KEY_P:
            st.chaos_palette = not st.chaos_palette
            schedule_palette(time.time()); st.report(True)
        elif key == glfw.KEY_E:
            st.chaos_effect = not st.chaos_effect
            schedule_effect(time.time()); st.report(True)
        elif key == glfw.KEY_T:
            # toggle all
            flag = not (st.auto_roll or st.chaos_rgb or st.chaos_palette or st.chaos_effect)
            st.auto_roll = st.chaos_rgb = st.chaos_palette = st.chaos_effect = flag
            now = time.time()
            schedule_rgb(now); schedule_palette(now); schedule_effect(now)
            st.report(True)
        elif key == glfw.KEY_9:
            st.roll_rate = max(0.0, st.roll_rate - 0.02); st.report(True)
        elif key == glfw.KEY_0:
            st.roll_rate = min(2.0, st.roll_rate + 0.02); st.report(True)

    glfw.set_key_callback(win, on_key)
    glClearColor(0.0, 0.0, 0.0, 1.0)

    # init schedules
    now = time.time()
    schedule_rgb(now); schedule_palette(now); schedule_effect(now)

    while not glfw.window_should_close(win):
        cur = time.time()
        dt = cur - last; last = cur
        if not st.paused:
            t_sim += dt * max(0.05, st.speed)

        # auto palette roll
        if st.auto_roll:
            st.shift += dt * st.roll_rate

        # chaos timers
        if st.chaos_rgb and cur >= st.next_rgb_change:
            st.rgb_gain = rand_gain()
            schedule_rgb(cur)
        else:
            # gently ease back towards 1.0 when chaos off
            if not st.chaos_rgb:
                st.rgb_gain = [g + (1.0 - g)*min(1.0, dt*0.8) for g in st.rgb_gain]

        if st.chaos_palette and cur >= st.next_palette_change:
            st.palette = random.randrange(5)
            schedule_palette(cur)

        if st.chaos_effect and cur >= st.next_effect_change:
            st.effect = random.randrange(6)
            schedule_effect(cur)

        # draw
        fbw, fbh = glfw.get_framebuffer_size(win)
        glViewport(0, 0, fbw, fbh)
        glClear(GL_COLOR_BUFFER_BIT)

        glUniform2f(loc_iRes, float(fbw), float(fbh))
        glUniform1f(loc_iTime, float(t_sim))
        glUniform1i(loc_effect, int(st.effect))
        glUniform1f(loc_speed, float(st.speed))
        glUniform1i(loc_pal, int(st.palette))
        glUniform1f(loc_shift, float(st.shift))
        glUniform3f(loc_gain, float(st.rgb_gain[0]), float(st.rgb_gain[1]), float(st.rgb_gain[2]))

        glDrawArrays(GL_TRIANGLES, 0, 3)

        glfw.swap_buffers(win)
        glfw.poll_events()

    glDeleteVertexArrays(1, [vao])
    glDeleteProgram(prog)
    glfw.terminate()

if __name__ == "__main__":
    main()
