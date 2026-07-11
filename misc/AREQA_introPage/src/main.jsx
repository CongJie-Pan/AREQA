import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import logo from './assets/areqa_logo_v2.png';
import icon from './assets/areqa_icon_v3.png';
import muse from './assets/Muse.png';
import './styles.css';

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
    body: '您可以要求AREQA扮演您學習路上的關鍵人物。不管是蘇格拉底、曹雪芹、牛頓、川端康成等人物，AREQA都能搖身一變化身，並且依照您的學習狀況寫信給您，您也可以與他回信。'
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
  useEffect(()=>{
    const onKey=(e)=>e.key==='Escape'&&setMenu(false);
    window.addEventListener('keydown',onKey); return()=>window.removeEventListener('keydown',onKey);
  },[]);
  return <>
    <header className="site-header" style={{justifyContent: 'center'}}>
      <a className="brand" href="#top" aria-label="AREQA 首頁"><img src={logo} alt="AREQA"/></a>
    </header>

    <main id="top">
      <section className="hero" id="about">
        <div className="star-field" aria-hidden="true"/>
        <div className="hero-copy">
          <p className="eyebrow">ADAPTIVE RAG-BASED EDUCATIONAL QA SYSTEM</p>
          <h1>懂你所學，<br/><em>伴你所讀。</em></h1>
          <p className="hero-lead">AREQA :一個博學、溫暖、理解您又善於引導的學伴。<br/>想學習任何東西嗎？就來找 AREQA 吧！</p>
          <div className="hero-actions"><a className="button primary" href="#contact">開始對話</a></div>
        </div>
        <div className="hero-art">
          <div className="muse-halo" aria-hidden="true"/>
          <img src={muse} alt="手持知識光球的繆思女神 AREQA 品牌插畫"/>
        </div>
      </section>

      <section className="demo-video-section">
        <div className="video-placeholder">
          <p>Demo Video Coming Soon</p>
        </div>
      </section>

      <section className="features-section" id="features">
        <div className="feature-grid-hermes">
          {features.map(f => (
            <article className="hermes-card" key={f.id} id={f.id === 'trace' ? 'transparency' : undefined}>
              <p className="hermes-eyebrow">{f.eyebrow}</p>
              <h3 className="hermes-title">
                {f.title.split('\n').map((line, i) => (
                  <React.Fragment key={i}>{line}<br/></React.Fragment>
                ))}
              </h3>
              <div className="hermes-image-placeholder">
                 <span>Image Placeholder</span>
              </div>
              <p className="hermes-body">{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="brand-interlude" aria-label="AREQA 品牌過場" id="contact">
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
