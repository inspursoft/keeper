import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { GitLabCiYaml } from './shared/shared.types';
import { map } from 'rxjs/operators';

@Injectable()
export class AppService {
  constructor(private http: HttpClient) {

  }

  getYamlFile(projectName: string): Observable<GitLabCiYaml> {
    return this.http.get('/api/v1/files', {
      params: {
        username: projectName.split('/')[0],
        project_name: projectName,
        file_path: '.gitlab-ci.yml'
      }
    }).pipe(map((res: object) => new GitLabCiYaml(Reflect.get(res, 'content'))));
  }

  addYamlFile(yamlStr: string, projectName: string): Observable<any> {
    return this.http.post('/api/v1/files',
      {content: yamlStr},
      {
        headers: {'Content-Type': 'application/json'},
        responseType: 'text',
        params: {
          username: projectName.split('/')[0],
          project_name: projectName,
          file_path: '.gitlab-ci.yml'
        }
      }
    );
  }

  updateYamlFile(yamlStr: string, projectName: string): Observable<any> {
    return this.http.put('/api/v1/files',
      {content: yamlStr},
      {
        headers: {'Content-Type': 'application/json'},
        responseType: 'text',
        params: {
          username: projectName.split('/')[0],
          project_name: projectName,
          file_path: '.gitlab-ci.yml'
        }
      }
    );
  }
}
