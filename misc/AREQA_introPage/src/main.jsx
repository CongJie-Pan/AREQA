import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import logo from './assets/areqa_logo_v2.png';
import icon from './assets/areqa_icon_v3.png';
import muse from './assets/Muse.png';
import pedagogicalPolicy from './assets/six_features/01_pedagogical_policy.png';
import asynchronousCare from './assets/six_features/02_asynchronous_care.png';
import persistentMemory from './assets/six_features/03_persistent_memory.png';
import activeAvatar from './assets/six_features/04_active_avatar.png';
import webSearchKnowledge from './assets/six_features/05_web_search_knowledge.png';
import intentExpansion from './assets/six_features/06_intent_expansion.png';
import './styles.css';

const featureImages = [
  pedagogicalPolicy,
  asynchronousCare,
  persistentMemory,
  activeAvatar,
  webSearchKnowledge,
  intentExpansion
];
const heroTitle = '懂你所學，\n伴你所讀。';
const promptSuggestions = [
  '我是 AREQA 您今天想學什麼嗎 ?',
  '今天心情如何，我可以陪你聊聊',
  '我是 AREQA 我可以幫您什麼嗎 ?'
];
const areqaAppUrl = 'https://areqa-frontend-aouk.onrender.com/';

const features = [
  {
    id: 'rag',
    eyebrow: '#1 PEDAGOGICAL POLICY',
    title: '動態鷹架\n認知策略',
    body: '拒絕給完答案就結束的「假性學習」。AREQA 會追蹤您的理解程度與情緒訊號，當漸入佳境時，自動將「完整解答」收攝為「提示與反問」，讓您獨立思考。'
  },
  {
    id: 'edf',
    eyebrow: '#2 ASYNCHRONOUS CARE',
    title: '主動關懷\n信箱回覆',
    body: 'AREQA不是冷冰冰的聊天機器人。AREQA 會記住您昨天的卡關與焦慮，在適當時機發送延遲信件給予提示與鼓勵。不打斷專注，溫柔地把學習線索送至您手上。'
  },
  {
    id: 'avatar',
    eyebrow: '#3 PERSISTENT MEMORY',
    title: '持續且長期的\n記憶系統',
    body: '真正有同理心的學習同伴。AREQA會濃縮你值得保留的學習偏好、易錯痛點與當前狀態，讓下一次對話能從既有的脈絡繼續，不再永遠從零開始。'
  },
  {
    id: 'gum',
    eyebrow: '#4 ACTIVE AVATAR',
    title: '即時\n角色扮演',
    body: '您可以要求AREQA扮演您學習路上的關鍵人物。不管是蘇格拉底、曹雪芹、牛頓、川端康成等人物，AREQA都能搖身一變，並依照您的學習狀況寫信給您，您也可以與他回信。'
  },
  {
    id: 'mailbox',
    eyebrow: '#5 WEB SEARCH KNOWLEDGE',
    title: '網路\n知識檢索',
    body: '整合關鍵字與外部搜尋。為每一句解答附上文獻依據與來源，給您可靠的知識地基。'
  },
  {
    id: 'trace',
    eyebrow: '#6 INTENT EXPANSION',
    title: '意圖擴寫\n洞察提問',
    body: '往往不知道該怎麼發問嗎？打下您的想法就好。AREQA 會自動擴寫您簡略的提問，精準捕捉沒說出口的學習盲點，引導您把問題問得更具體、更深入。'
  }
];
function App(){
  const [menu, setMenu] = useState(false);
  const [typedTitle, setTypedTitle] = useState('');
  const [animatedPlaceholder, setAnimatedPlaceholder] = useState('');
  const [prompt, setPrompt] = useState('');
  useEffect(()=>{
    const onKey=(e)=>e.key==='Escape'&&setMenu(false);
    window.addEventListener('keydown',onKey); return()=>window.removeEventListener('keydown',onKey);
  },[]);
  useEffect(() => {
    const animatedElements = document.querySelectorAll('[data-reveal]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.16 });

    animatedElements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setTypedTitle(heroTitle);
      return undefined;
    }

    const characters = Array.from(heroTitle);
    let characterIndex = 0;
    let typingTimer;
    const startTimer = window.setTimeout(() => {
      typingTimer = window.setInterval(() => {
        characterIndex += 1;
        setTypedTitle(characters.slice(0, characterIndex).join(''));
        if (characterIndex === characters.length) window.clearInterval(typingTimer);
      }, 82);
    }, 220);

    return () => {
      window.clearTimeout(startTimer);
      window.clearInterval(typingTimer);
    };
  }, []);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setAnimatedPlaceholder(promptSuggestions[0]);
      return undefined;
    }

    let suggestionIndex = 0;
    let characterIndex = 0;
    let isDeleting = false;
    let placeholderTimer;

    const animatePlaceholder = () => {
      const characters = Array.from(promptSuggestions[suggestionIndex]);

      if (!isDeleting) {
        characterIndex += 1;
        setAnimatedPlaceholder(characters.slice(0, characterIndex).join(''));

        if (characterIndex === characters.length) {
          isDeleting = true;
          placeholderTimer = window.setTimeout(animatePlaceholder, 1800);
          return;
        }
      } else {
        characterIndex -= 1;
        setAnimatedPlaceholder(characters.slice(0, characterIndex).join(''));

        if (characterIndex === 0) {
          isDeleting = false;
          suggestionIndex = (suggestionIndex + 1) % promptSuggestions.length;
          placeholderTimer = window.setTimeout(animatePlaceholder, 360);
          return;
        }
      }

      placeholderTimer = window.setTimeout(animatePlaceholder, isDeleting ? 28 : 58);
    };

    placeholderTimer = window.setTimeout(animatePlaceholder, 420);
    return () => window.clearTimeout(placeholderTimer);
  }, []);

  const openAreqaApp = (event) => {
    event.preventDefault();
    window.location.assign(areqaAppUrl);
  };

  const [typedFirstLine = '', typedSecondLine = ''] = typedTitle.split('\n');
  return <>
    <header className="site-header" style={{justifyContent: 'center'}}>
      <a className="brand" href="#top" aria-label="AREQA 首頁"><img src={logo} alt="AREQA"/></a>
    </header>

    <main id="top">
      <div className="knowledge-thread" aria-hidden="true">
        <svg viewBox="0 0 1440 3600" preserveAspectRatio="none">
          <path d="M1280 0 C1180 430 1370 620 1110 920 S720 1280 960 1640 S1250 2150 810 2480 S300 2990 690 3600" />
          <g>
            <circle cx="1128" cy="890" r="5" />
            <circle cx="922" cy="1580" r="4" />
            <circle cx="846" cy="2450" r="5" />
            <circle cx="646" cy="3490" r="4" />
          </g>
        </svg>
      </div>
      <div className="celestial-field" aria-hidden="true">
        <span className="celestial-star" /><span className="celestial-orbit" />
        <span className="celestial-dot" /><span className="celestial-star" />
        <span className="celestial-orbit" /><span className="celestial-dot" />
        <span className="celestial-star" /><span className="celestial-orbit" />
        <span className="celestial-dot" /><span className="celestial-star" />
        <span className="celestial-dot" /><span className="celestial-orbit" />
        <span className="celestial-star" /><span className="celestial-dot" />
        <span className="celestial-star" /><span className="celestial-orbit" />
        <span className="celestial-dot" /><span className="celestial-star" />
      </div>
      <section className="hero" id="about">
        <div className="star-field" aria-hidden="true"/>
        <div className="hero-copy">
          <p className="eyebrow">ADAPTIVE RAG-BASED EDUCATIONAL QA SYSTEM</p>
          <h1 aria-label="懂你所學，伴你所讀。">
            <span aria-hidden="true">
              {typedFirstLine}
              {!typedTitle.includes('\n') && <i className="typing-cursor" />}
              <br/>
              <em>{typedSecondLine}</em>
              {typedTitle.includes('\n') && <i className="typing-cursor" />}
            </span>
          </h1>
          <p className="hero-lead">AREQA :一個博學、溫暖、理解您又善於引導的學伴。<br/>想學習任何東西嗎？就來找 AREQA 吧！</p>
          <form
            className="prompt-launcher"
            onSubmit={openAreqaApp}
          >
            <input
              type="text"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={animatedPlaceholder}
              aria-label="輸入想和 AREQA 對話的內容"
              autoComplete="off"
            />
            <button className="prompt-submit" type="submit" aria-label="前往 AREQA 送出訊息">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" /></svg>
            </button>
          </form>
        </div>
        <div className="hero-art">
          <div className="muse-halo" aria-hidden="true"/>
          <img src={muse} alt="手持知識光球的繆思女神 AREQA 品牌插畫"/>
        </div>
      </section>

      <section className="demo-video-section">
        <div className="section-texture demo-texture" aria-hidden="true" />
        <div className="video-placeholder">
          <p>Demo Video Coming Soon</p>
        </div>
      </section>

      <section className="features-section" id="features">
        <div className="section-texture features-texture" aria-hidden="true" />
        <div className="feature-grid-hermes">
          {features.map((f, index) => (
            <article className="hermes-card" key={f.id} id={f.id === 'trace' ? 'transparency' : undefined} data-reveal>
              <span className="card-corner card-corner-top" aria-hidden="true" />
              <span className="card-corner card-corner-bottom" aria-hidden="true" />
              <p className="hermes-eyebrow">{f.eyebrow}</p>
              <h3 className="hermes-title">
                {f.title.split('\n').map((line, i) => (
                  <React.Fragment key={i}>{line}<br/></React.Fragment>
                ))}
              </h3>
              <img
                className="hermes-feature-image"
                src={featureImages[index]}
                alt={`${f.title.replace('\n', '')}特色插畫`}
              />
              <p className="hermes-body">{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="brand-interlude" aria-label="AREQA 品牌過場" id="contact" data-reveal>
        <div className="closing-astrolabe" aria-hidden="true">
          <i /><i /><i />
        </div>
        <img src={icon} alt="AREQA 品牌圖標" className="closing-icon" />
        <div className="poster-text"><span>A</span><span>R</span><span>E</span><span>Q</span><span>A</span></div>
        <h2 className="closing-slogan">懂你所學，伴你所讀。</h2>
        <p className="eyebrow">Your Eureka Moment, Our Companionship.</p>
      </section>
    </main>

    <footer>
      <small>© 2026 AREQA. All rights reserved.</small>
    </footer>
  </>
}

createRoot(document.getElementById('root')).render(<App/>);
