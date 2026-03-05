import React from 'react';
import { useLocation } from 'react-router-dom';
import type { SectionBlockStatus } from '../config/workspaceSections';
import { getWorkspaceSectionByPath } from '../config/workspaceSections';
import './WorkspaceSectionPage.css';

const statusLabelMap: Record<SectionBlockStatus, string> = {
  skeleton: '骨架完成',
  planned: '规划中',
  next: '下一步',
};

const WorkspaceSectionPage: React.FC = () => {
  const location = useLocation();
  const section = getWorkspaceSectionByPath(location.pathname);

  return (
    <div className="workspace-section-page">
      <section className="workspace-section-highlights" aria-label="模块目标">
        <p className="workspace-section-side-title">当前模块目标</p>
        <ul className="workspace-section-highlight-list">
          {section.highlights.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="workspace-section-grid" aria-label={`${section.label}功能骨架`}>
        {section.blocks.map((block, index) => (
          <article
            key={block.title}
            className="workspace-section-card"
            data-status={block.status}
            style={{ animationDelay: `${index * 80}ms` }}
          >
            <span className="workspace-section-card-status">{statusLabelMap[block.status]}</span>
            <h3>{block.title}</h3>
            <p>{block.description}</p>
            <span className="workspace-section-card-index">{String(index + 1).padStart(2, '0')}</span>
          </article>
        ))}
      </section>

      <section className="workspace-section-next" aria-label="下一步建议">
        <p className="workspace-section-next-label">建议开发顺序</p>
        <p className="workspace-section-next-text">{section.nextAction}</p>
      </section>
    </div>
  );
};

export default WorkspaceSectionPage;
