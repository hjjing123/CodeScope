import { describe, expect, it } from 'vitest';

import { compactFilePath, formatCompactLocation, formatLocation } from './findingLocation';

describe('findingLocation', () => {
  it('keeps short paths unchanged', () => {
    expect(compactFilePath('src/main/resources/application.properties')).toBe(
      'src/main/resources/application.properties'
    );
  });

  it('compacts long paths to the trailing segments', () => {
    expect(compactFilePath('src/main/java/com/xq/tmall/service/impl/UserServiceImpl.java')).toBe(
      '.../tmall/service/impl/UserServiceImpl.java'
    );
  });

  it('formats full and compact locations with line numbers', () => {
    expect(formatLocation('src/main/java/com/xq/tmall/dao/UserMapper.java', 16)).toBe(
      'src/main/java/com/xq/tmall/dao/UserMapper.java:16'
    );
    expect(formatCompactLocation('src/main/java/com/xq/tmall/dao/UserMapper.java', 16)).toBe(
      '.../xq/tmall/dao/UserMapper.java:16'
    );
  });
});
