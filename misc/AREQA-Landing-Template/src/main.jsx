import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import logo from './assets/areqa_logo_v2.png';
import icon from './assets/areqa_icon_v3.png';
import muse from './assets/Muse.png';
import './styles.css';

const features = [
  {
    id: 'rag',
    eyebrow: '01 · VERIFIED KNOWLEDGE',
    title: '混合知識檢索',
    body: '整合向量、關鍵字與外部搜尋，將回答連回可追溯的來源，而不是只給一段看似合理的文字。',
    demo: 'rag'
  },
  {
    id: 'edf',
    eyebrow: '02 · PEDAGOGICAL POLICY',
    title: '學習者認知策略',
    body: '依照理解程度與挫折訊號調整說明深度，從完整鷹架逐步退場，避免「看懂就以為學會」。',
    demo: 'edf'
  },
  {
    id: 'avatar',
    eyebrow: '03 · ACTIVE AVATAR',
    title: '大師角色對話',
    body: '以蘇格拉底式追問或柏拉圖式觀點切入，讓抽象概念成為可以持續追問的思辨歷程。',
    demo: 'avatar'
  },
  {
    id: 'gum',
    eyebrow: '04 · LONG-TERM MEMORY',
    title: '冷熱雙軌記憶',
    body: '濃縮值得保留的偏好、主題與學習狀態，使下一次對話能從既有脈絡繼續，而非重新開始。',
    demo: 'gum'
  },
  {
    id: 'mailbox',
    eyebrow: '05 · ASYNC CARE',
    title: '主動關懷信箱',
    body: '在適當時機整理未完成的問題，以延遲信件與站內通知，把學習線索溫柔地送回你手上。',
    demo: 'mailbox'
  },
  {
    id: 'trace',
    eyebrow: '06 · EVIDENCE TRACE',
    title: '回答依據與推理脈絡',
    body: '呈現參考來源、關鍵判斷與尚待確認之處，讓你不只得到答案，也知道答案憑什麼成立。',
    demo: 'trace'
  }
];

function MiniUI({ type }) {
  const [avatar, setAvatar] = useState('socrates');
  if (type === 'rag') return (
    <div className="mini-ui chat-demo" aria-label="引用來源介面示意">
      <div className="mini-top"><span className="dot"/><span>Answer with evidence</span><span className="live">LIVE</span></div>
      <p>「知識」不只是一個結論，也包含它形成的脈絡與可查證依據。</p>
      <div className="citation-row"><button>[1] 蘇格拉底對話錄</button><button>[2] 教育哲學導論</button></div>
    </div>
  );
  if (type === 'edf') return (
    <div className="mini-ui state-demo">
      <div className="state-head"><span>學習狀態</span><strong>需要引導</strong></div>
      <div className="meter"><i style={{width:'62%'}}/></div>
      <div className="policy"><small>策略切換</small><p>完整詳解 → 一步提示＋反問</p></div>
      <blockquote>「先找出題目中不會改變的條件，好嗎？」</blockquote>
    </div>
  );
  if (type === 'avatar') return (
    <div className="mini-ui avatar-demo">
      <div className="avatar-tabs" role="tablist" aria-label="角色切換">
        <button className={avatar==='socrates'?'active':''} onClick={()=>setAvatar('socrates')}>Σ</button>
        <button className={avatar==='plato'?'active':''} onClick={()=>setAvatar('plato')}>Π</button>
      </div>
      <small>{avatar==='socrates'?'蘇格拉底模式':'柏拉圖模式'}</small>
      <p>{avatar==='socrates'?'「在回答之前，我們先檢查你所說的『理解』究竟指什麼。」':'「讓我們從現象背後的結構，重新看待這個問題。」'}</p>
    </div>
  );
  if (type === 'gum') return (
    <div className="mini-ui memory-demo">
      <div className="memory-title"><span>Learning Memory</span><small>剛剛更新</small></div>
      <div className="tags"><span>#偏好具體例子</span><span>#避免艱澀術語</span><span>#文言文學習中</span></div>
      <div className="memory-note"><span>可管理</span><p>你可以檢視、修改或移除被保留的記憶。</p></div>
    </div>
  );
  if (type === 'mailbox') return (
    <div className="mini-ui mail-demo">
      <div className="envelope"><div className="flap"/><span>1</span></div>
      <div><small>來自蘇格拉底的一封信</small><h4>關於你昨天停下來的那一題</h4><p>我整理了一個更小的切入點，等你準備好時再回來。</p></div>
    </div>
  );
  return (
    <details className="mini-ui trace-demo">
      <summary><span>查看回答依據</span><b>＋</b></summary>
      <div className="trace-line"><span>參考來源</span><p>2 篇教材、1 筆課堂筆記</p></div>
      <div className="trace-line"><span>關鍵判斷</span><p>先區分概念定義，再比對例外條件</p></div>
      <div className="trace-line"><span>尚待確認</span><p>教材版本與老師採用術語</p></div>
    </details>
  );
}

function App(){
  const [menu, setMenu] = useState(false);
  useEffect(()=>{
    const onKey=(e)=>e.key==='Escape'&&setMenu(false);
    window.addEventListener('keydown',onKey); return()=>window.removeEventListener('keydown',onKey);
  },[]);
  return <>
    <header className="site-header">
      <a className="brand" href="#top" aria-label="AREQA 首頁"><img src={logo} alt="AREQA"/></a>
      <button className="menu-button" onClick={()=>setMenu(!menu)} aria-expanded={menu} aria-controls="main-nav"><span/><span/></button>
      <nav id="main-nav" className={menu?'open':''}>
        <a href="#about" onClick={()=>setMenu(false)}>關於 AREQA</a>
        <a href="#features" onClick={()=>setMenu(false)}>核心能力</a>
        <a href="#transparency" onClick={()=>setMenu(false)}>學習透明度</a>
        <a className="nav-cta" href="#contact">進入學習大廳</a>
      </nav>
    </header>

    <main id="top">
      <section className="hero" id="about">
        <div className="star-field" aria-hidden="true"/>
        <div className="hero-copy">
          <p className="eyebrow">ADAPTIVE RAG-BASED EDUCATIONAL QA SYSTEM</p>
          <h1>懂你所學，<br/><em>伴你所讀。</em></h1>
          <p className="hero-lead">AREQA 不只回答問題，也會理解你的學習狀態、保留重要脈絡，並以可靠來源陪你建立真正可延續的理解。</p>
          <div className="hero-actions"><a className="button primary" href="#contact">開始對話</a><a className="button ghost" href="#features">探索核心能力 <span>↓</span></a></div>
          <div className="trust-line"><span>可驗證引用</span><i/><span>適性教學策略</span><i/><span>延續學習脈絡</span></div>
        </div>
        <div className="hero-art">
          <div className="muse-halo" aria-hidden="true"/>
          <img src={muse} alt="手持知識光球的繆思女神 AREQA 品牌插畫"/>
        </div>
      </section>

      <section className="value-section">
        <p>教育不是一次回答，<br/>而是理解逐步被喚醒的過程。</p>
        <span>AREQA，陪你把每一次提問，連成可延續的學習旅程。</span>
      </section>

      <section className="features-section" id="features">
        <div className="section-heading"><div><p className="eyebrow">SIX CORE CAPABILITIES</p><h2>不是另一個聊天框，<br/>而是一套真正為學習設計的系統。</h2></div><p>每一項能力都以真實產品介面邏輯呈現，從來源、狀態、記憶到主動關懷，讓智慧發生在學習脈絡裡。</p></div>
        <div className="feature-grid">
          {features.map(f=><article className="feature-card" key={f.id} id={f.id==='trace'?'transparency':undefined}>
            <p className="feature-eyebrow">{f.eyebrow}</p><h3>{f.title}</h3><p className="feature-body">{f.body}</p><MiniUI type={f.demo}/>
          </article>)}
        </div>
      </section>

      <section className="brand-interlude" aria-label="AREQA 品牌過場"><span>A</span><span>R</span><span>E</span><span>Q</span><span>A</span><p>Your Eureka Moment, Our Companionship.</p></section>

      <section className="closing" id="contact">
        <img src={icon} alt="AREQA 品牌圖標"/>
        <p className="eyebrow">YOUR NEXT LEARNING MOMENT</p>
        <h2>讓下一次提問，<br/>不再從零開始。</h2>
        <p>從一個問題開始，讓 AREQA 陪你留下脈絡、建立理解，並在真正需要時提供剛剛好的引導。</p>
        <a className="button primary" href="mailto:hello@areqa.app">進入學習大廳</a>
      </section>
    </main>

    <footer><div className="footer-brand"><img src={logo} alt="AREQA"/><p>可靠、溫暖，能延續學習脈絡的教育型 AI 學伴。</p></div><div className="footer-links"><a href="#about">關於 AREQA</a><a href="#features">核心能力</a><a href="#transparency">學習透明度</a></div><small>© 2026 AREQA. All rights reserved.</small></footer>
  </>
}

createRoot(document.getElementById('root')).render(<App/>);
