import React from 'react';
import { createStyles } from 'antd-style';
import { Button, Space, Typography } from 'antd';
import { MessageSquarePlus } from 'lucide-react';
import { motion } from 'framer-motion';

const { Text } = Typography;

const useStyles = createStyles(({ token, css }) => ({
  container: {
    marginTop: token.marginMD,
    padding: token.paddingSM,
    borderTop: `1px solid ${token.colorBorderSecondary}`,
    width: '100%',
  },
  title: {
    display: 'flex',
    alignItems: 'center',
    gap: token.marginXXS,
    marginBottom: token.marginSM,
    fontSize: token.fontSizeSM,
    color: token.colorTextSecondary,
  },
  questionButton: css`
    text-align: left;
    height: auto;
    white-space: normal;
    padding: ${token.paddingXS}px ${token.paddingMD}px;
    border-radius: ${token.borderRadiusLG}px;
    background: ${token.colorBgContainer};
    border: 1px solid ${token.colorBorder};
    transition: all 0.2s ease;
    font-size: ${token.fontSize}px;
    
    &.ant-btn:hover {
      background: ${token.colorPrimary} !important;
      border-color: ${token.colorPrimary} !important;
      color: #fff !important;
      transform: translateY(-1px);
      box-shadow: ${token.boxShadowTertiary};
    }
  `,
}));

interface SuggestedQuestionsProps {
  suggestions: string[];
  onSelect: (question: string) => void;
  disabled?: boolean;
}

export const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({
  suggestions,
  onSelect,
  disabled = false,
}) => {
  const { styles } = useStyles();

  if (!suggestions || suggestions.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.2 }}
      className={styles.container}
    >
      <div className={styles.title}>
        <MessageSquarePlus size={14} />
        <Text type="secondary">您可能還想了解：</Text>
      </div>
      <Space orientation="vertical" style={{ width: '100%' }} size="small">
        {suggestions.map((question, index) => (
          <Button
            key={index}
            className={styles.questionButton}
            onClick={() => onSelect(question)}
            disabled={disabled}
            block
          >
            {question}
          </Button>
        ))}
      </Space>
    </motion.div>
  );
};
