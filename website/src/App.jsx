import { useState } from 'react'
import './App.css'

const ASCII_LOGO = `   __                      __        __
  / /____  _________ ___  / /_____  / /__
 / __/ _ \\/ ___/ __ \`__ \\/ __/ __ \\/ //_/
/ /_/  __/ /  / / / / / / /_/ /_/ / ,<
\\__/\\___/_/  /_/ /_/ /_/\\__/\\____/_/|_|`

const TERMINAL_PREVIEW = `$ termtok --search cats
[termtok] streaming youtube shorts: cats
[termtok] fetched 3/12 videos into cache

▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
▀▄▄▀▀▄▄▀▄▀▀▀▄▀▀▄▀▄▄▀▀▄▀▀▄▄▀▀▄▀▀▄▄▀▀▄▄▀▀
▄▀▀▄▄▀▀▄▄▄▀▄▄▀▀▄▄▀▀▀▄▄▀▄▀▀▄▄▀▄▀▀▄▄▀▀▄▀▄
▀▄▀▀▄▄▀▀▄▀▀▄▄▀▀▄▀▄▄▀▀▄▄▀▄▀▄▀▀▄▄▀▄▀▀▄▀▄▀
▄▄▀▀▄▀▄▄▀▄▄▀▀▄▀▀▄▄▀▄▀▀▄▄▀▀▄▄▀▀▄▄▀▄▀▀▄▄▀
▀▄▄▀▄▀▀▄▄▀▀▄▀▄▄▀▀▄▄▀▀▄▀▄▄▀▄▀▀▄▄▀▀▄▀▄▄▀▀
▄▀▀▄▄▀▄▀▀▀▄▀▀▄▄▀▄▀▀▄▄▀▄▀▀▄▄▀▀▄▄▀▄▀▀▄▄▀▄
▀▄▄▀▀▄▄▀▀▄▄▀▀▄▀▄▄▀▄▀▀▄▄▀▄▀▀▄▄▀▄▀▀▄▄▀▀▄▀
▀▀▄▄▀▄▀▄▀▀▄▄▀▀▄▀▄▀▀▄▄▀▀▄▄▀▀▄▄▀▀▄▄▀▀▄▀▄▄

  ▶ 1/∞   🔊 70%   [████████░░] 0:08`

const FEATURES = [
  {
    icon: '▶',
    title: 'Vertical scroll feed',
    desc: 'Momentum physics, snap-to-video, the whole deal. Your wrist will hate you.',
  },
  {
    icon: '♪',
    title: 'Audio playback',
    desc: 'Real audio via ffplay. Your coworkers will definitely think you\'re working.',
  },
  {
    icon: '⚡',
    title: 'YouTube & TikTok',
    desc: 'Streams live. No account needed for YouTube. TikTok requires a stolen cookie.',
  },
  {
    icon: '📁',
    title: 'Local folders',
    desc: 'Point it at a folder of videos. Offline doom-scrolling. A true innovation.',
  },
]

const CURL_INSTALL = `curl -fsSL https://raw.githubusercontent.com/kazymirrabier/termtok/main/install.sh | sh`

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="text-xs px-2 py-1 rounded border border-[#00ff41]/30 text-[#00ff41]/60 hover:text-[#00ff41] hover:border-[#00ff41] transition-colors cursor-pointer"
    >
      {copied ? 'copied!' : 'copy'}
    </button>
  )
}

function CodeBlock({ children, copyText }) {
  return (
    <div className="relative bg-[#111] border border-[#1a1a1a] rounded-lg p-4 text-sm text-[#00ff41]/80 font-mono overflow-x-auto">
      {copyText && (
        <div className="absolute top-3 right-3">
          <CopyButton text={copyText} />
        </div>
      )}
      <pre className="leading-relaxed">{children}</pre>
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e0e0e0] font-mono">
      <div className="scanline" />

      {/* Hero */}
      <section className="min-h-screen flex flex-col items-center justify-center px-6 text-center relative">
        <div className="mb-6 text-[#00ff41] terminal-glow text-[10px] sm:text-xs leading-tight whitespace-pre select-none">
          {ASCII_LOGO}
        </div>

        <p className="text-[#00ff41] text-xl sm:text-2xl font-bold terminal-glow cursor-blink mb-4">
          Doomscroll right in your terminal
        </p>

        <p className="text-[#666] text-sm sm:text-base max-w-lg mb-8">
          A TikTok-style vertical video feed rendered in your terminal using truecolor half-block pixels.
          {' '}Because life is short and your attention span is shorter.
        </p>

        <div className="flex flex-wrap gap-3 justify-center mb-16">
          <a
            href="https://github.com/kazymirrabier/termtok"
            target="_blank"
            rel="noreferrer"
            className="px-5 py-2 bg-[#00ff41] text-black font-bold text-sm rounded hover:bg-[#00cc33] transition-colors"
          >
            View on GitHub
          </a>
          <a
            href="#install"
            className="px-5 py-2 border border-[#00ff41]/40 text-[#00ff41] text-sm rounded hover:border-[#00ff41] transition-colors"
          >
            Get started →
          </a>
        </div>

        <div className="w-full max-w-2xl bg-[#111] border border-[#1a1a1a] rounded-lg overflow-hidden shadow-2xl">
          <div className="flex items-center gap-1.5 px-4 py-3 bg-[#161616] border-b border-[#1a1a1a]">
            <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
            <span className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
            <span className="w-3 h-3 rounded-full bg-[#28c840]" />
            <span className="ml-3 text-xs text-[#444]">termtok — 80×24</span>
          </div>
          <pre className="p-4 text-[11px] sm:text-xs text-[#00ff41]/80 leading-snug overflow-x-auto">
            {TERMINAL_PREVIEW}
          </pre>
        </div>

        <p className="mt-4 text-[#333] text-xs">↑ artist's impression. real resolution may vary.</p>
      </section>

      {/* Features */}
      <section className="py-20 px-6 max-w-5xl mx-auto">
        <h2 className="text-[#00ff41] text-lg mb-2 text-center terminal-glow">// features</h2>
        <p className="text-[#444] text-sm text-center mb-10">things it does, roughly in order of impressiveness</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map(f => (
            <div
              key={f.title}
              className="bg-[#111] border border-[#1a1a1a] rounded-lg p-5 card-hover"
            >
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="text-[#00ff41] text-sm font-bold mb-2">{f.title}</h3>
              <p className="text-[#666] text-xs leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Install */}
      <section id="install" className="py-20 px-6 max-w-3xl mx-auto w-full">
        <h2 className="text-[#00ff41] text-lg mb-2 terminal-glow">// install</h2>
        <p className="text-[#444] text-sm mb-8">pick your poison.</p>

        <div className="space-y-6">
          {/* curl */}
          <div>
            <p className="text-[#555] text-xs mb-2 uppercase tracking-widest">one-liner</p>
            <CodeBlock copyText={CURL_INSTALL}>
              {CURL_INSTALL}
            </CodeBlock>
          </div>

          {/* manual */}
          <div>
            <p className="text-[#555] text-xs mb-2 uppercase tracking-widest">manual</p>
            <div className="space-y-3">
              <CodeBlock copyText="git clone https://github.com/kazymirrabier/termtok && cd termtok && uv venv .venv && uv pip install --python .venv/bin/python -r requirements-player.txt">
{`git clone https://github.com/kazymirrabier/termtok
cd termtok
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-player.txt`}
              </CodeBlock>
              <CodeBlock copyText="brew install ffmpeg">
{`brew install ffmpeg          # audio (optional but you'll want it)`}
              </CodeBlock>
              <CodeBlock copyText="uv pip install --python .venv/bin/python yt-dlp curl_cffi && brew install deno">
{`uv pip install --python .venv/bin/python yt-dlp curl_cffi
brew install deno             # streaming support`}
              </CodeBlock>
            </div>
          </div>
        </div>
      </section>

      {/* Usage */}
      <section className="py-20 px-6 max-w-3xl mx-auto w-full">
        <h2 className="text-[#00ff41] text-lg mb-2 terminal-glow">// usage</h2>
        <p className="text-[#444] text-sm mb-8">it's basically just <code className="text-[#00ff41]/60">./bin/termtok</code> with flags</p>

        <div className="space-y-2 text-sm">
          {[
            ['./bin/termtok', 'trending YouTube Shorts (the default)'],
            ['./bin/termtok --search cats', 'search YouTube Shorts'],
            ['./bin/termtok --user MrBeast', "a channel's Shorts"],
            ['./bin/termtok --tag funny', 'by hashtag'],
            ['./bin/termtok -p tiktok', 'TikTok For-You feed (needs ms_token)'],
            ['./bin/termtok /path/to/clips', 'local folder — fully offline'],
          ].map(([cmd, label]) => (
            <div key={cmd} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 bg-[#111] border border-[#1a1a1a] rounded px-4 py-3 card-hover">
              <code className="text-[#00ff41]/80 text-xs whitespace-nowrap flex-shrink-0">{cmd}</code>
              <span className="text-[#444] text-xs"># {label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[#1a1a1a] py-10 px-6 text-center space-y-3">
        <div>
          <a
            href="https://x.com/KazymirR"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 text-[#00ff41]/50 hover:text-[#00ff41] text-xs transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.748l7.73-8.835L1.254 2.25H8.08l4.259 5.63 5.905-5.63zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            follow @KazymirR
          </a>
        </div>
        <p className="text-[#222] text-xs">MIT license — use it, break it, don't blame us</p>
        <a
          href="https://github.com/kazymirrabier/termtok"
          target="_blank"
          rel="noreferrer"
          className="text-[#333] hover:text-[#00ff41]/40 text-xs transition-colors"
        >
          github.com/kazymirrabier/termtok
        </a>
      </footer>
    </div>
  )
}
