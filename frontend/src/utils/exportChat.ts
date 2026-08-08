// @ts-expect-error - file-saver types might be missing in some environments
import { saveAs } from 'file-saver';
import { Document, Paragraph, TextRun, Packer } from 'docx';
import type { DisplayMessage } from '@/store/chat';
import type { ImageBlock } from '@/database/schema';

export const formatSourcesForMarkdown = (message: DisplayMessage): string => {
  if (!message.sources?.length) return '';
  const lines = message.sources
    .map((source, index) => {
      const url = source.url || (source.chunk_id?.startsWith('http') ? source.chunk_id : '');
      let domain = '';
      try {
        domain = url ? new URL(url).hostname : '';
      } catch {
        domain = '';
      }
      const label = source.title || domain || `來源 ${index + 1}`;
      return url ? `${index + 1}. [${label}](${url})` : `${index + 1}. ${label}`;
    });
  return `#### 文獻來源\n\n${lines.join('\n')}\n\n`;
};

const markdownLine = (value: string | undefined | null): string => {
  return String(value || '').trim();
};

const markdownList = (items: string[] | undefined, indent = ''): string => {
  if (!items?.length) return '';
  return items
    .map((item) => markdownLine(item))
    .filter(Boolean)
    .map((item) => `${indent}- ${item}`)
    .join('\n');
};

const formatImageBlockForMarkdown = (block: ImageBlock, index: number): string => {
  const lines: string[] = [];
  const title = markdownLine(block.topic || block.caption || `圖片 ${index + 1}`);
  const imageUrl = markdownLine(block.imageUrl || block.thumbnailUrl);
  const sourceUrl = markdownLine(block.sourceUrl);

  lines.push(`##### 圖片 ${index + 1}: ${title}`);
  if (imageUrl) {
    lines.push(`![${title}](${imageUrl})`);
    lines.push(`- 圖片 URL: ${imageUrl}`);
  }
  if (markdownLine(block.caption)) lines.push(`- 圖說: ${block.caption}`);
  if (sourceUrl) lines.push(`- 來源: [${block.sourceDomain || sourceUrl}](${sourceUrl})`);
  if (markdownLine(block.provider)) lines.push(`- Provider: ${block.provider}`);
  if (markdownLine(block.license)) lines.push(`- 授權: ${block.license}`);
  if (markdownLine(block.creator)) lines.push(`- 作者: ${block.creator}`);
  if (markdownLine(block.attributionString)) lines.push(`- Attribution: ${block.attributionString}`);
  if (markdownLine(block.visionSummary)) lines.push(`- 圖像理解摘要: ${block.visionSummary}`);
  if (markdownLine(block.visionConfidence)) lines.push(`- 圖像理解信心: ${block.visionConfidence}`);

  const visibleElements = markdownList(block.visibleElements, '  ');
  if (visibleElements) {
    lines.push('- 圖中可見元素:');
    lines.push(visibleElements);
  }

  const howToRead = markdownList(block.howToRead, '  ');
  if (howToRead) {
    lines.push('- 讀圖方式:');
    lines.push(howToRead);
  }

  const limitations = markdownList(block.visionLimitations, '  ');
  if (limitations) {
    lines.push('- 圖像理解限制:');
    lines.push(limitations);
  }

  return `${lines.join('\n')}\n\n`;
};

export const formatAnswerBlocksForMarkdown = (message: DisplayMessage): string => {
  const imageBlocks = (message.answerBlocks || []).filter(
    (block): block is ImageBlock => block.type === 'image_block'
  );
  if (!imageBlocks.length) return '';

  return `#### 圖片資訊\n\n${imageBlocks
    .map((block, index) => formatImageBlockForMarkdown(block, index))
    .join('')}`;
};

export const exportToMarkdown = (messages: DisplayMessage[]) => {
  let content = '# AREQA 對話紀錄\n\n';
  
  messages.forEach(msg => {
    const roleName = msg.role === 'user' ? '👤 您' : '🤖 AREQA';
    content += `### ${roleName}\n`;
    
    if (msg.reasoning && msg.reasoning.content) {
      content += `> **🤔 思考過程：**\n> \n> ${msg.reasoning.content.split('\n').join('\n> ')}\n\n`;
    }
    
    content += `${msg.content}\n\n`;
    content += formatAnswerBlocksForMarkdown(msg);
    content += formatSourcesForMarkdown(msg);
    content += '---\n\n';
  });

  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  saveAs(blob, `areqa-chat-${new Date().toISOString().slice(0, 10)}.md`);
};

export const exportToDocx = async (messages: DisplayMessage[]) => {
  const children: Paragraph[] = [
    new Paragraph({
      children: [
        new TextRun({ text: 'AREQA 對話紀錄', bold: true, size: 32 }),
      ],
      spacing: { after: 400 }
    })
  ];

  messages.forEach(msg => {
    const roleName = msg.role === 'user' ? '👤 您' : '🤖 AREQA';
    
    // Add Role Header
    children.push(
      new Paragraph({
        children: [
          new TextRun({ text: roleName, bold: true, size: 28, color: msg.role === 'user' ? '2B579A' : 'd8a25c' })
        ],
        spacing: { before: 200, after: 100 }
      })
    );

    // Process content line by line to support basic line breaks
    const lines = msg.content.split('\n');
    lines.forEach(line => {
      children.push(
        new Paragraph({
          children: [
            new TextRun({ text: line, size: 24 })
          ],
          spacing: { after: 100 }
        })
      );
    });

    if (msg.sources?.length) {
      children.push(new Paragraph({
        children: [new TextRun({ text: '文獻來源', bold: true, size: 24 })],
        spacing: { before: 120, after: 80 },
      }));
      msg.sources.forEach((source, index) => {
        const url = source.url || (source.chunk_id?.startsWith('http') ? source.chunk_id : '');
        const label = source.title || `來源 ${index + 1}`;
        children.push(new Paragraph({
          children: [new TextRun({ text: `${index + 1}. ${label}${url ? ` — ${url}` : ''}`, size: 20 })],
          spacing: { after: 60 },
        }));
      });
    }

    // Add separator
    children.push(
      new Paragraph({
        children: [
          new TextRun({ text: '----------------------------------------', color: 'CCCCCC' })
        ],
        spacing: { before: 200, after: 200 }
      })
    );
  });

  const doc = new Document({
    sections: [{
      properties: {},
      children: children
    }]
  });

  const blob = await Packer.toBlob(doc);
  saveAs(blob, `areqa-chat-${new Date().toISOString().slice(0, 10)}.docx`);
};

export const exportToPdf = async () => {
  // Using dynamic import because html2pdf needs window
  const html2pdf = (await import('html2pdf.js')).default;
  
  // Find the message list container
  const element = document.querySelector('#export-chat-container');
  if (!element) {
    throw new Error('找不到對話內容');
  }

  // Clone it to manipulate styles without affecting the UI
  const clonedElement = element.cloneNode(true) as HTMLElement;
  clonedElement.style.height = 'auto';
  clonedElement.style.overflow = 'visible';
  clonedElement.style.padding = '20px';
  clonedElement.style.color = '#000'; // Make text dark for PDF readability
  clonedElement.style.backgroundColor = '#fff';

  // Add a title
  const title = document.createElement('h1');
  title.innerText = 'AREQA 對話紀錄';
  title.style.textAlign = 'center';
  title.style.marginBottom = '20px';
  title.style.color = '#000';
  clonedElement.insertBefore(title, clonedElement.firstChild);

  const opt = {
    margin:       10,
    filename:     `areqa-chat-${new Date().toISOString().slice(0, 10)}.pdf`,
    image:        { type: 'jpeg' as const, quality: 0.98 },
    html2canvas:  { scale: 2, useCORS: true },
    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' as const }
  };

  html2pdf().set(opt).from(clonedElement).save();
};
