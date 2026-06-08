import React, { useState } from 'react';
import { Proposition, useStore } from '../store/useStore';
import { Edit2, Trash2, Check, X, ShieldAlert } from 'lucide-react';

interface MemoryTableProps {
  propositions: Proposition[];
}

const MemoryTable: React.FC<MemoryTableProps> = ({ propositions }) => {
  const { updateMemory, deleteMemory } = useStore();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [editConfidence, setEditConfidence] = useState(5);

  const startEdit = (p: Proposition) => {
    setEditingId(p.id);
    setEditText(p.text);
    setEditConfidence(p.confidence || 5);
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async (id: number) => {
    await updateMemory(id, editText, editConfidence);
    setEditingId(null);
  };

  const handleDelete = async (id: number) => {
    if (confirm('Are you sure you want to delete this memory proposition? This will erase it from GUM.')) {
      await deleteMemory(id);
    }
  };

  if (propositions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 bg-[#1e1e1e] border border-[#2d2d2d] rounded-xl text-center">
        <ShieldAlert size={40} className="text-gray-600 mb-3" />
        <h4 className="text-sm font-semibold text-gray-400 mb-1">No Propositions Logged</h4>
        <p className="text-xs text-gray-500 max-w-xs leading-relaxed">
          Start recording to let GUM build propositions about your preferences, context, and intent.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#1e1e1e] border border-[#2d2d2d] rounded-xl overflow-hidden shadow-lg">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-[#151515] border-b border-[#2d2d2d] text-gray-500 text-[10px] font-bold uppercase tracking-wider select-none">
              <th className="py-4 px-6">Proposition</th>
              <th className="py-4 px-6 w-28 text-center">Support</th>
              <th className="py-4 px-6 w-28 text-center">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2d2d2d] text-sm">
            {propositions.map((p) => {
              const isEditing = editingId === p.id;
              return (
                <tr key={p.id} className="hover:bg-[#252525]/30 transition-colors">
                  <td className="py-4 px-6">
                    {isEditing ? (
                      <div className="space-y-2">
                        <input
                          type="text"
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          className="w-full bg-[#151515] border border-[#3d3d3d] rounded-md px-3 py-1.5 text-white text-sm focus:outline-none focus:border-amber-500/50"
                        />
                      </div>
                    ) : (
                      <span className="text-gray-300 font-medium">{p.text}</span>
                    )}
                  </td>
                  <td className="py-4 px-6 text-center">
                    {isEditing ? (
                      <select
                        value={editConfidence}
                        onChange={(e) => setEditConfidence(parseInt(e.target.value))}
                        className="bg-[#151515] border border-[#3d3d3d] rounded-md px-2 py-1 text-white text-xs focus:outline-none"
                      >
                        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((num) => (
                          <option key={num} value={num}>
                            {num}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="inline-flex items-center justify-center px-2 py-0.5 rounded text-xs font-bold bg-[#151515] text-amber-500 border border-[#2d2d2d]">
                        {p.confidence ?? 'N/A'}
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-6 text-center">
                    <div className="flex justify-center space-x-2">
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => saveEdit(p.id)}
                            className="p-1.5 bg-emerald-600/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-600/20 rounded-md transition-colors"
                            title="Save"
                          >
                            <Check size={14} />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="p-1.5 bg-[#2a2a2a] text-gray-400 border border-[#3a3a3a] hover:text-white rounded-md transition-colors"
                            title="Cancel"
                          >
                            <X size={14} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(p)}
                            className="p-1.5 text-gray-500 hover:bg-[#252525] hover:text-white rounded-md transition-colors"
                            title="Edit"
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            onClick={() => handleDelete(p.id)}
                            className="p-1.5 text-gray-500 hover:bg-red-950/20 hover:text-red-400 rounded-md transition-colors"
                            title="Delete"
                          >
                            <Trash2 size={14} />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default MemoryTable;
