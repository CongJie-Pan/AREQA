import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createClient } from '@supabase/supabase-js';
import { notFound } from 'next/navigation';
import styles from './styles.module.css';

export const dynamic = 'force-dynamic';

const SHARE_TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,80}$/;

interface SharedAnswerBlock {
  type: 'paragraph' | 'image_block';
  text?: string;
  imageUrl?: string;
  sourceUrl?: string;
  sourceDomain?: string;
  caption?: string;
  explanatoryCaption?: string;
}

interface SharedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  answerBlocks?: SharedAnswerBlock[] | null;
  citations?: string[] | null;
  createdAt: string;
}

interface SharedConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: SharedMessage[];
}

interface SharePageProps {
  params: Promise<{ token: string }>;
}

function createPublicSupabaseClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) return null;

  return createClient(url, anonKey, {
    auth: {
      persistSession: false,
    },
  });
}

async function getSharedConversation(token: string): Promise<SharedConversation | null> {
  if (!SHARE_TOKEN_PATTERN.test(token)) return null;

  const supabase = createPublicSupabaseClient();
  if (!supabase) return null;

  const { data, error } = await supabase.rpc('get_public_conversation_share', {
    p_share_token: token,
  });

  if (error || !data) return null;
  return data as SharedConversation;
}

function renderAnswerBlocks(blocks: SharedAnswerBlock[]) {
  return blocks.map((block, index) => {
    if (block.type === 'paragraph' && block.text) {
      return (
        <ReactMarkdown key={`paragraph-${index}`} remarkPlugins={[remarkGfm]}>
          {block.text}
        </ReactMarkdown>
      );
    }

    if (block.type === 'image_block' && block.imageUrl) {
      return (
        <figure className={styles.imageBlock} key={`image-${index}`}>
          {/* Shared answer images can come from many attributed providers, so Next Image cannot use a stable allowlist here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={block.imageUrl} alt={block.caption || block.explanatoryCaption || ''} />
          {(block.caption || block.explanatoryCaption || block.sourceUrl) && (
            <figcaption>
              {block.explanatoryCaption || block.caption}
              {block.sourceUrl && (
                <>
                  {' '}
                  <a href={block.sourceUrl} rel="noreferrer" target="_blank">
                    {block.sourceDomain || 'Source'}
                  </a>
                </>
              )}
            </figcaption>
          )}
        </figure>
      );
    }

    return null;
  });
}

export default async function SharePage({ params }: SharePageProps) {
  const { token } = await params;
  const conversation = await getSharedConversation(token);

  if (!conversation) notFound();

  return (
    <main className={styles.page}>
      <section className={styles.shell}>
        <header className={styles.header}>
          <div className={styles.brand}>AREQA</div>
          <h1>{conversation.title || 'Shared conversation'}</h1>
        </header>

        <div className={styles.messages}>
          {conversation.messages.map((message) => (
            <article className={styles.message} data-role={message.role} key={message.id}>
              <div className={styles.role}>{message.role === 'user' ? 'User' : 'AREQA'}</div>
              <div className={styles.bubble}>
                {message.answerBlocks && message.answerBlocks.length > 0 ? (
                  renderAnswerBlocks(message.answerBlocks)
                ) : (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                )}
                {message.citations && message.citations.length > 0 && (
                  <div className={styles.citations}>
                    {message.citations.map((citation) => (
                      <a href={citation} key={citation} rel="noreferrer" target="_blank">
                        {citation}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
